# coding: utf-8

"""
Helpers for making HTTP requests within FME.

The main class of interest is :class:`FMERequestsSession`.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

# PR72320/PR72321: Import this now, to guarantee that worker threads can access it.
# Needed when running with standard-library-in-zip (i.e. embedded Python) and using
# Requests in threads.
# See http://stackoverflow.com/a/13057751 and
# https://github.com/kennethreitz/requests/issues/3578.
# noinspection PyUnresolvedReferences
import encodings.idna

import json
import logging
import os
import re
import sys
import warnings
from collections import namedtuple

import fme
import requests
import urllib3
from fmeobjects import FMEException, FMESession, FME_ASSEMBLY_VERSION
from pypac import PACSession
from requests.adapters import HTTPAdapter
from requests.auth import HTTPProxyAuth, HTTPBasicAuth, HTTPDigestAuth
from six.moves.urllib.parse import urlparse, quote

from . import tr
from .logfile import get_configured_logger
from .utils import choice_to_bool
from .parsers import stringarray_to_dict

# PR65941: Disable lower-level SSL warnings.
# https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
urllib3.disable_warnings()


_GENERIC_LOGGER_NAME = "FMERequestsSession"


# A proxy config of empty string tells Requests to ignore environment proxies too.
# Tested with Fiddler.
_REQUESTS_NO_PROXY_CONFIG = {"http": "", "https": ""}


def _get_env_var(var_name_lowercase):
    """
    Look for an environment variable, first looking for the lowercase
    version, then the uppercase version if lowercase was missing/empty.

    This is how Requests handles proxy environment variable resolution.

    :param str var_name_lowercase: The environment variable name.
    """
    return os.environ.get(var_name_lowercase) or os.environ.get(
        var_name_lowercase.upper()
    )


def _toggle_http_debug_logging(enabled):
    """
    Globally toggle debug logging in urllib3 and the standard library's HTTP client.
    """
    level = logging.DEBUG if enabled else logging.INFO
    logging.getLogger("urllib3").setLevel(level)
    logging.getLogger("http.client").setLevel(level)
    try:
        from http import client

        client.HTTPConnection.debuglevel = 1 if enabled else 0
    except ImportError:
        pass  # PY2


class SystemCertStoreAdapter(HTTPAdapter):
    """
    An HTTPAdapter that makes Requests use the system certificate store
    on Windows and Python 3 instead of the bundled root CAs from certifi.

    Python 3.4+ defaults to using the Windows Certificate Store on Windows.
    urllib3 falls back to Python's default certificate store if no CA bundle is given.
    But Requests always passes the certifi bundle to urllib3, which this adapter undoes.

    This class is a no-op for:
    - Python 2.7, because there's no fallback on Windows without certifi.
    - MacOS, as Python 3.6+ stopped using Apple's OpenSSL and so can't use the keychain.
      Therefore the system certificate store as seen by Python could be empty.
      certifi is recommended by Python maintainers.
      See https://bugs.python.org/issue28150.
    - Linux, because certifi from the system package manager should be an alias to the
      system certificate store, like it is on CentOS and Debian.
    """

    # See also:
    # https://github.com/psf/requests/issues/5316#issuecomment-604518757
    # https://urllib3.readthedocs.io/en/latest/reference/index.html#urllib3.connection.VerifiedHTTPSConnection
    def cert_verify(self, conn, url, verify, cert):
        # Let the overloaded method do all its config for urllib3:
        # set urllib3 behaviour for `verify` flag, and resolve certifi CAs
        super(SystemCertStoreAdapter, self).cert_verify(conn, url, verify, cert)
        # If applicable, undo certifi config so urllib3 falls back to system cert store.
        if sys.version_info.major > 2 and sys.platform == "win32":
            conn.ca_certs = None
            conn.ca_cert_dir = None


class FMERequestsSession(PACSession):
    """
    A wrapper around Requests that adds FME-specific functionality around HTTP requests,
    such as proxy configuration based on Workbench settings.

    HTTP access in FME should use this class instead of :class:`requests.Session`.

    The superclass transparently provides Proxy Auto-Config (PAC) file services.
    This can be disabled by one of these methods:

    * Setting :attr:`pypac.PACSession.pac_enabled` to False after instantiation.
    * Setting Proxy Options to No Proxy in Workbench Options.
    * Setting Proxy Options to Use System Proxy, and setting up general proxies in
      Internet Options such that :class:`FMESession` returns these proxies.
      This skips PAC discovery, which saves some time,
      and avoids having to decide between using the PAC or falling back to
      general proxy settings for each request.

    :ivar int request_count: Increments every time a request is made.
    """

    def __init__(self, log=None, fme_session=None):
        """
        :param log: Python standard library logger to use. If None, a default is used.
        :param FMESession fme_session: Load proxy configuration from this session.
            Intended for testing purposes only.
            Defaults to a new :class:`FMESession` instance.
        """
        super(FMERequestsSession, self).__init__()
        adapter = SystemCertStoreAdapter()
        self.mount("http://", adapter)
        self.mount("https://", adapter)

        self._log_prefix = self.__class__.__name__
        self._log = log or get_configured_logger(self._log_prefix)

        self._general_proxy_config, self._custom_proxy_map = self._load_proxy_settings(
            fme_session or FMESession()
        )
        self._last_used_custom_proxy = None

        self.request_count = 0

        # PR62339: Include FME version in User-Agent. Same format as FME core.
        self.headers["User-Agent"] = "FME/%s %s" % (
            FME_ASSEMBLY_VERSION,
            self.headers.get("User-Agent"),
        )

        # FMEENGINE-68435: Set library debug logging based on workspace debug flags.
        try:
            _toggle_http_debug_logging(
                "HTTP_DEBUG" in fme.macroValues.get("FME_DEBUG", "")
            )
        except AttributeError:
            pass

    def _load_proxy_settings(self, fme_session):
        """
        Load all proxy configuration from the given FMESession, as well as
        from environment variables.

        If proxies are configured using environment variables, mention it in the log.
        Proxy environment variables are honoured by Requests,
        but this method does not set them.
        Instead, this class expects them to be set in FME's fmesite.py startup script.

        :param FMESession fme_session: Load proxy configuration from this session.
        :returns: FMEGeneralProxyHandler, FMECustomProxyMapHandler
        :raises UnsupportedProxyAuthenticationMethod:
            If the proxy authentication method for the environment proxy is unsupported.
        """
        # Get the configured HTTP/HTTPS proxies, if any, and log about their use.
        # If both HTTP and HTTPS are configured and they're identical, log once.
        # Otherwise, log whatever is configured.
        http_proxy = _get_env_var("http_proxy")
        https_proxy = _get_env_var("https_proxy")
        if http_proxy is not None and http_proxy == https_proxy:
            self._log_proxy(http_proxy)
        else:
            if http_proxy:
                self._log_proxy(http_proxy)
            if https_proxy:
                self._log_proxy(https_proxy)

        # Load the top-level proxy configuration.
        general_proxy_config = FMEGeneralProxyHandler()
        general_proxy_config.configure(fme_session)
        self.pac_enabled = general_proxy_config.use_pac

        # If proxies are configured, or PAC is enabled, and a proxy username specified,
        # then ensure the proxy authentication method is supported.
        enforce_proxy_auth_method = (
            general_proxy_config.use_pac or general_proxy_config.proxies
        ) and general_proxy_config.user
        if enforce_proxy_auth_method and not self._is_proxy_auth_method_supported(
            general_proxy_config.auth_method
        ):
            raise UnsupportedProxyAuthenticationMethod(
                self._log_prefix, general_proxy_config.auth_method
            )

        # Configure PyPAC with proxy credentials, if any.
        if general_proxy_config.user:
            self.proxy_auth = HTTPProxyAuth(
                general_proxy_config.user, general_proxy_config.password
            )

        # PR70705: Honour system proxy exceptions on Windows.
        if general_proxy_config.proxies and os.name == "nt":
            _configure_proxy_exceptions()

        # PR70807: FME Custom Proxy Map.
        custom_proxy_map = FMECustomProxyMapHandler()
        custom_proxy_map.configure(fme_session)

        return general_proxy_config, custom_proxy_map

    def _log_proxy(self, proxy_url):
        """Log about a proxy being used."""
        self._log.info(tr("Using proxy %s"), proxy_url_without_credentials(proxy_url))

    @staticmethod
    def _is_proxy_auth_method_supported(auth_method):
        """
        :returns: True if there's no proxy authentication or if it's Basic.
            Other methods, like NTLM and Digest, aren't supported.
        """
        return not auth_method or auth_method.lower() == "basic"

    def request(self, method, url, **kwargs):
        """
        Make a request.

        Proxy resolution order:

        * `proxies` keyword argument
        * FME Custom Proxy Map
        * Proxy Auto-Config file
        * Proxy environment variables

        The `NO_PROXY` environment variable may override any proxy selected above.

        :param str method: GET|POST|HEAD|PUT|DELETE
        :param str url: URL to request
        :param kwargs: keyword arguments passed straight to Requests
        :rtype: requests.Response
        """
        self.request_count += 1

        # PR62730: Specify a default timeout, to prevent possibility of waiting forever.
        kwargs.setdefault("timeout", 60)

        # FMEENGINE-63687: Non-proxy hosts.
        if not kwargs.get("proxies"):
            try:
                if self._general_proxy_config.is_non_proxy_host(urlparse(url).hostname):
                    self._log.debug(tr("Non-Proxy Hosts: Directly accessing '%s'"), url)
                    kwargs["proxies"] = _REQUESTS_NO_PROXY_CONFIG
            except ValueError:
                pass  # Ignore malformed URLs.

        # PR70807: FME Custom Proxy Map.
        # Only use custom proxy map if caller did not specify any proxies.
        if not kwargs.get("proxies"):
            custom_proxy = self._custom_proxy_map.custom_proxy_for_url(url)
            if custom_proxy and not custom_proxy.proxy_url:
                self._log.debug(tr("Custom Proxy Map: Directly accessing '%s'"), url)
                kwargs["proxies"] = _REQUESTS_NO_PROXY_CONFIG
            elif custom_proxy:
                self._log.debug(
                    tr(
                        "Custom Proxy Map: Using proxy '{proxy_url}' for URL '{original_url}'"
                    ).format(
                        proxy_url=custom_proxy.sanitized_proxy_url, original_url=url
                    )
                )
                if not self._is_proxy_auth_method_supported(custom_proxy.auth_method):
                    raise UnsupportedProxyAuthenticationMethod(
                        self._log_prefix, custom_proxy.auth_method
                    )
                kwargs["proxies"] = {
                    "http": custom_proxy.proxy_url,
                    "https": custom_proxy.proxy_url,
                }
                # Log about the custom proxy every time it changes to a different proxy.
                if self._last_used_custom_proxy != custom_proxy.sanitized_proxy_url:
                    self._last_used_custom_proxy = custom_proxy.sanitized_proxy_url
                    self._log_proxy(custom_proxy.sanitized_proxy_url)

        return super(FMERequestsSession, self).request(method, url, **kwargs)


class KerberosUnsupportedException(FMEException):
    """For use in :func:`getRequestsKerberosAuthObject`."""

    def __init__(self, log_prefix):
        """
        :param str log_prefix: Name of caller to use in the log message.
        """
        base_message = tr(
            "%s: Kerberos authentication on this system requires the installation for a Kerberos library for Python. "
            + "Otherwise, try NTLM authentication if it's enabled by the host, or please visit http://www.safe.com/support"
        )
        message = base_message % log_prefix
        super(KerberosUnsupportedException, self).__init__(message)


def get_kerberos_auth(caller_name):
    """
    Try to get a Kerberos authentication object to use with :mod:`requests`. Raises
    a user-friendly exception if dependencies couldn't be loaded.

    :param str caller_name: Prefix to use in error message if Kerberos not available.
    :rtype: requests_kerberos.HTTPKerberosAuth
    :raises KerberosUnsupportedException:
        If an ImportError occurred when trying to import :mod:`requests_kerberos`.
       This is most likely because the `kerberos` module isn't available.
    """
    try:
        import requests_kerberos as rk

        # PR78426: Disable mutual auth to work with some customer configs.
        return rk.HTTPKerberosAuth(
            mutual_authentication=rk.DISABLED,
        )
    except ImportError:
        raise KerberosUnsupportedException(caller_name)


def get_auth_object(auth_type, user="", password="", caller_name=""):
    """
    Get a :class:`requests.auth.AuthBase` object configured for use with Requests.

    :param str auth_type: The type of authentication object to obtain.
        Must be one of: `None`, `Kerberos`, `Basic`, `Digest`, `NTLM`. Case insensitive.
    :param str user: Ignored if not applicable to the specified auth type.
    :param str password: Ignored if not applicable to the specified auth type.
    :param str caller_name: Caller's name for log messages.
    :return: The configured authentication object.
    :rtype: requests.auth.AuthBase or None
    :raises ValueError: if authentication type is unrecognized.
    """
    auth_type = auth_type.upper()
    # These types don't need a username and password.
    if auth_type == "NONE":
        return None
    elif auth_type == "KERBEROS":
        return get_kerberos_auth(caller_name)

    # These types need a username and password.
    if auth_type == "BASIC":
        return HTTPBasicAuth(user, password)
    elif auth_type == "DIGEST":
        return HTTPDigestAuth(user, password)
    elif auth_type == "NTLM":
        from requests_ntlm import HttpNtlmAuth

        return HttpNtlmAuth(user, password)
    else:
        raise ValueError(tr("Unknown authentication type '%s'") % auth_type)


def proxy_url_without_credentials(proxy_url):
    """
    Given a proxy URL, return it with any proxy credentials removed.

    :param str proxy_url: The proxy url.
    """
    credentials_separator_index = proxy_url.rfind("@")
    if credentials_separator_index > -1:
        # Strip out credentials if they're present.
        proxy_url = (
            proxy_url[: proxy_url.find("://") + 3]
            + proxy_url[credentials_separator_index + 1 :]
        )
    return proxy_url


# For FMESession.getProperties(). For the result format, see fmesession.h getProxy().
FMESESSION_PROP_NETWORK_PROXY = "fme_session_prop_network_proxy"
FMESESSION_PROP_NETWORK_PROXY_SETTINGS = "fme_session_prop_network_proxy_settings"
FMEProxyDefinition = namedtuple(
    "FMEProxyDefinition", ["env_var", "proxy_url", "auth_method"]
)
FMECustomProxyMap = namedtuple(
    "FMECustomProxyMap",
    [
        "url",
        "proxy_url",
        "sanitized_proxy_url",
        "requires_auth",
        "user",
        "password",
        "auth_method",
    ],
)


class FMEGeneralProxyHandler(object):
    """
    Handles parsing of the proxy settings that apply to all requests by default.

    :type proxies: list[FMEProxyDefinition]
    :ivar proxies: List of general proxy configs.
    :type non_proxy_hosts: list[re.Pattern]
    :ivar non_proxy_hosts: Skip proxies for any matching hostname regex.
    :ivar bool use_pac: Whether to search for and honour PAC files.
    :ivar str user: Proxy username.
    :ivar str password: Proxy password.
    :ivar str auth_method: Proxy authentication method.
    """

    def __init__(self):
        self.proxies = []
        self.non_proxy_hosts = []
        self.use_pac = True
        self.user = ""
        self.password = ""
        self._auth_method = None

    def configure(self, fme_session):
        """Load general proxy configuration from FME.

        :param FMESession fme_session: Configuration is loaded from this.
        """
        proxy_config = fme_session.getProperties(FMESESSION_PROP_NETWORK_PROXY, {})
        use_system_proxy = False
        i = 0
        while i < len(proxy_config):
            key, value = proxy_config[i], proxy_config[i + 1]
            if (
                key in {"http_proxy", "https_proxy", "ftp_proxy"}
                and proxy_config[i + 2] == "proxy_auth_method"
            ):
                # Proxy values are not FME-encoded.
                self.proxies.append(
                    FMEProxyDefinition(key, value, proxy_config[i + 3].lower())
                )
                i += 4
                continue
            if key == "use-system-proxy":
                use_system_proxy = choice_to_bool(value)
            if key == "non_proxy_hosts":
                try:
                    for host_regex in json.loads(value):
                        self.non_proxy_hosts.append(re.compile(host_regex, re.I))
                except (json.JSONDecodeError, re.error):
                    warnings.warn(tr("FME non-proxy-hosts: not JSON or bad regex"))
            i += 2

        # Use System Proxy plus presence of general proxies implies that PAC
        # Use System Proxy but no general proxies must mean to find and honour any PAC.
        self.use_pac = use_system_proxy and not self.proxies

        # Grab proxy credentials from Workbench.
        # When a PAC is in use, we need these standalone values.
        proxy_network_config = stringarray_to_dict(
            fme_session.getProperties(FMESESSION_PROP_NETWORK_PROXY_SETTINGS, {})
        )
        self.user = proxy_network_config.get("system-proxy-user", self.user)
        self.password = proxy_network_config.get("system-proxy-password", self.password)
        self._auth_method = proxy_network_config.get(
            "system-proxy-authentication-method", self._auth_method
        )

    @property
    def auth_method(self):
        """
        Get the proxy authentication method, either at the system-level
        settings, or the one from the first general proxy config (if any).

        In practice, these values should be identical. They may differ
        in unit tests that provide incomplete mock configs.
        """
        if self._auth_method:
            return self._auth_method
        if self.proxies:
            return self.proxies[0].auth_method
        return None

    def is_non_proxy_host(self, host):
        """
        :param host: Hostname to evaluate. Case-insensitive.
        :return: True if the given hostname matches one configured to use no proxy.
        """
        if not host:
            return False
        return any(map(lambda host_re: host_re.match(host), self.non_proxy_hosts))


class FMECustomProxyMapHandler(object):
    """
    Handles parsing of the FME Custom Proxy Map, which assigns proxies for
    specific URLs.
    """

    # See PR70807.

    def __init__(self):
        self._custom_proxy_map = []

    def custom_proxy_for_url(self, url):
        """
        Consult the FME custom proxy map for a proxy configuration to use
        for the given URL. It's up to the caller to handle the proxy
        authentication method.

        :param str url: URL for which to find a custom proxy mapping. Case-insensitive.
        :returns: Custom proxy map entry matching the given URL,
            or `None` if there's no match.
        :rtype: FMECustomProxyMap
        """
        url = url.lower()
        for proxyMap in self._custom_proxy_map:
            if url.startswith(proxyMap.url):
                return proxyMap
        return None

    def configure(self, fme_session):
        """
        Load Custom Proxy Map configuration from FME.

        :param FMESession fme_session: Configuration is loaded from this.
        """
        proxy_config = fme_session.getProperties(FMESESSION_PROP_NETWORK_PROXY, {})
        i = 0
        while i < len(proxy_config):
            key, value = proxy_config[i], proxy_config[i + 1]
            if key == "source-url" and proxy_config[i + 2] == "proxy-info":
                self._custom_proxy_map.append(
                    self.parse_custom_proxy_map(fme_session, value, proxy_config[i + 3])
                )
                i += 4
                continue
            i += 2

    @staticmethod
    def parse_custom_proxy_map(fme_session, url, proxy_info):
        """
        Parse a serialized custom proxy map configuration entry from FME.

        :param FMESession fme_session: For decoding FME-encoded strings.
        :param str url: FME-encoded URL for the custom proxy map.
        :param str proxy_info: FME-encoded and comma-delimited proxy configuration for
            the custom proxy map.
        :rtype: FMECustomProxyMap
        """
        url = fme_session.decodeFromFMEParsableText(url).lower()

        proxy_map_info = stringarray_to_dict(proxy_info.split(","))
        proxy_url = fme_session.decodeFromFMEParsableText(
            proxy_map_info["proxy-url"]
        ).strip()
        if not proxy_url:
            # A proxy mapping that means 'do not use proxy for this URL'.
            return FMECustomProxyMap(url, "", "", False, "", "", "")
        elif not proxy_url.lower().startswith("http"):
            # FME Server gives proxy hostname only. Assume a scheme.
            proxy_url = "http://{}".format(proxy_url)
        parsed_proxy = urlparse(proxy_url)

        netloc = (
            parsed_proxy.hostname + ":" + proxy_map_info["proxy-port"]
        )  # Port never present in proxy-url.
        sanitized_proxy_url = "{}://{}".format(
            parsed_proxy.scheme, netloc
        )  # No credentials and no path.
        user = fme_session.decodeFromFMEParsableText(proxy_map_info["user"])
        password = fme_session.decodeFromFMEParsableText(proxy_map_info["password"])
        requires_authentication = choice_to_bool(
            proxy_map_info["requires-authentication"]
        )

        proxy_url_with_creds = sanitized_proxy_url
        if requires_authentication:
            # Only put credentials into proxy URL if proxy authentication is enabled.
            # urllib doesn't make it easy to ask it to assemble a URL with credentials.
            creds = ""
            if user:
                creds = quote(user)
                if password:
                    creds += ":" + quote(password)
                creds += "@"
            proxy_url_with_creds = "{}://{}{}".format(
                parsed_proxy.scheme, creds, netloc
            )

        return FMECustomProxyMap(
            url,
            proxy_url_with_creds,
            sanitized_proxy_url,
            requires_authentication,
            user,
            password,
            proxy_map_info["authentication-method"].lower(),
        )


class UnsupportedProxyAuthenticationMethod(FMEException):
    """For use in :class:`FMERequestsSession`."""

    def __init__(self, log_prefix, auth_method):
        """
        :param str log_prefix: The prefix to use for all log messages from this class,
            e.g. "[format name] [direction]".
        :param str auth_method: Proxy authentication method.
        """
        message = tr(
            "{prefix}: Proxy authentication mode '{auth_method}' is not supported by this format"
        )
        super(UnsupportedProxyAuthenticationMethod, self).__init__(
            message.format(prefix=log_prefix, auth_method=auth_method)
        )


def _configure_proxy_exceptions():
    """
    Set the `NO_PROXY` environment variable based on Windows Internet Options.
    Requests and other Python HTTP libraries should automatically
    honour this environment variable.
    No-op on non-Windows, or if `NO_PROXY` is already set.

    :returns: True if proxy settings were picked up from the Windows Registry
       and the `NO_PROXY` environment variable was set using it.
    :rtype: bool
    """
    if _get_env_var("no_proxy") or os.name != "nt":
        return False

    try:
        import winreg
    except ImportError:
        import _winreg as winreg  # PY2.

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            overrides = winreg.QueryValueEx(key, "ProxyOverride")[0]
    except WindowsError:
        return False

    overrides = [entry.strip() for entry in overrides.split(";")]
    no_proxy_entries = list(
        filter(lambda entry: entry not in ("<local>", "<-loopback>"), overrides)
    )
    if len(no_proxy_entries) < len(overrides):
        no_proxy_entries.extend(["localhost", "127.0.0.1", "::1"])
    os.environ["no_proxy"] = ", ".join(no_proxy_entries)
    return True
