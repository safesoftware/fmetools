from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import os
import re
import sys
import warnings
from collections import namedtuple

import fme
from fmeobjects import FMEException, FMESession, FME_ASSEMBLY_VERSION

import requests
from pypac import PACSession
from requests.auth import AuthBase, HTTPProxyAuth
from requests.exceptions import SSLError
from requests.packages import urllib3
from requests.adapters import HTTPAdapter

from fmegeneral.fmeconstants import (
    kFME_MSGNUM_PROXY_AUTH_MODE_UNSUPPORTED,
    kFME_MSGNUM_SSL_CERTIFICATE_VERIFY_FAILED,
    kFME_MSGNUM_USING_PROXY,
)
from fmegeneral import fmelog

from six.moves.urllib.parse import urlparse, quote

from fmegeneral.fmeutil import stringArrayToDict, choiceToBool

# PR72320/PR72321: Import this now, to guarantee that worker threads can access it.
# Needed when running with standard-library-in-zip (i.e. embedded Python) and using Requests in threads.
# See http://stackoverflow.com/a/13057751 and https://github.com/kennethreitz/requests/issues/3578.
# noinspection PyUnresolvedReferences
import encodings.idna

# PR65941: Disable lower-level SSL warnings.
# https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
urllib3.disable_warnings()

GENERIC_LOGGER_NAME = "FMERequestsSession"
_no_prepend_args = {"no_prepend_args": True}

# For FMESession.getProperties(). For the result format, see fmesession.h getProxy().
FMESESSION_PROP_NETWORK_PROXY = "fme_session_prop_network_proxy"
FMESESSION_PROP_NETWORK_PROXY_SETTINGS = "fme_session_prop_network_proxy_settings"
# Proxy environment variables.
ENV_HTTP_PROXY = "http_proxy"
ENV_HTTPS_PROXY = "https_proxy"
ENV_NO_PROXY = "no_proxy"

REQUEST_DEFAULT_TIMEOUT = 60

# A proxy config of empty string tells Requests to ignore environment proxies too. Tested with Fiddler.
REQUESTS_NO_PROXY_CONFIG = {"http": "", "https": ""}


def get_env_var(var_name_lowercase):
    """Look for an environment variable, first looking for the lowercase
    version, then the uppercase version if lowercase was missing/empty.

    This is how Requests handles proxy environment variable resolution.

    :param str var_name_lowercase: The environment variable name.
    """
    return os.environ.get(var_name_lowercase) or os.environ.get(var_name_lowercase.upper())


def toggle_http_debug_logging(enabled):
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
    urllib3 will fall back to Python's default certificate store if no CA bundle is given.
    However, Requests always passes the certifi bundle to urllib3, which this adapter undoes.

    This class is a no-op for:
    - Python 2.7, because there's no fallback on Windows without certifi.
    - MacOS, because Python 3.6+ stopped using Apple's OpenSSL and so can't access the keychain.
      Therefore the system certificate store as seen by Python could be empty.
      certifi is recommended by Python maintainers. See https://bugs.python.org/issue28150.
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
        # If not on PY2, then undo certifi config so urllib3 falls back to system cert store.
        if sys.version_info.major > 2 and sys.platform == "win32":
            conn.ca_certs = None
            conn.ca_cert_dir = None


class FMERequestsSession(PACSession):
    """A wrapper around Requests that adds some FME-specific functionality that
    any web-accessing code would want, such as proxy configuration based on
    Workbench settings, and SSL certificate verification fallback.

    The superclass transparently provides Proxy Auto-Config file services.
    This can be disabled by one of these methods:

    * Setting :attr:`pypac.PACSession.pac_enabled` to False after instantiation.
    * Setting Proxy Options to No Proxy in Workbench Options.
    * Setting Proxy Options to Use System Proxy, and setting up general proxies in Internet Options
      such that :class:`FMESession` returns these proxies.
      This removes the performance impact of searching for a PAC when it's unlikely to exist,
      and avoids having to decide between honouring PAC or falling back to general proxy settings for each request.

    Any internal code running through FME that intends to use Requests should use this wrapper instead.

    :ivar int requestCount: Increments every time a request is made.
    """

    def __init__(self, logPrefix, log=None, fmeSession=None, legacy_verify_mode=True):
        """

        :param str logPrefix: The prefix to use for all log messages from this class, e.g. "[format name] [direction]".
        :param fmelog.FMELoggerAdapter log: Python standard library logger to use.
           If provided, it *must* be able to gracefully handle FME message numbers
           or otherwise not propagate integer messages to handlers that cannot handle it (like the root logger).
           If None, a generic Logger instance is instantiated, which won't output anything to the FME log.
        :param FMESession fmeSession: Load proxy configuration from this session. Intended for testing purposes only.
           If not provided, a new FMESession object is used for this purpose.
        :param bool legacy_verify_mode: If true, then certificate verification failure
           will warn, disable certificate verification in this session, and retry the request.
           Starting in FME 2021.1, certificate verification should be toggled by
           the "Verify SSL Certificates" option added to all Named Connections by FMEDESKTOP-10332.
        """
        super(FMERequestsSession, self).__init__()
        adapter = SystemCertStoreAdapter()
        for scheme in ("http://", "https://"):
            self.mount(scheme, adapter)

        self.logPrefix = logPrefix

        self._log = log
        if not self._log:
            self._log = fmelog.get_configured_logger(GENERIC_LOGGER_NAME)

        self._generalProxyConfig, self._customProxyMap = self._loadProxySettings(
            fmeSession if fmeSession else FMESession()
        )
        self._lastUsedCustomProxy = None

        self._legacy_verify_mode = legacy_verify_mode
        self.requestCount = 0

        # PR62339: Include FME version in User-Agent. Same format as in our HTTP library for C++.
        self.headers["User-Agent"] = "FME/%s %s" % (
            FME_ASSEMBLY_VERSION,
            self.headers.get("User-Agent"),
        )

        # FMEENGINE-68435: Toggle library-level debug logging based on workspace debug flags.
        try:
            toggle_http_debug_logging("HTTP_DEBUG" in fme.macroValues.get("FME_DEBUG", ""))
        except AttributeError:
            pass

    def _loadProxySettings(self, fmeSession):
        """Load all proxy configuration from the given FMESession, as well as
        from environment variables.

        If proxies are configured using environment variables, mention it in the log.
        Proxy environment variables are honoured by Requests, but this method does not set them.
        Instead, this class expects them to be set in the fmesite.py startup script.

        :param FMESession fmeSession: Load proxy configuration from this session.
        :returns: FMEGeneralProxyHandler, FMECustomProxyMapHandler
        :raises UnsupportedProxyAuthenticationMethod:
           If the proxy authentication method for the environment proxy is unsupported.
        """
        # Get the configured HTTP/HTTPS proxies, if any, and log about their use.
        # If both HTTP and HTTPS are configured and they're identical, log once.
        # Otherwise, log whatever is configured.
        httpProxy = get_env_var(ENV_HTTP_PROXY)
        httpsProxy = get_env_var(ENV_HTTPS_PROXY)
        if httpProxy is not None and httpProxy == httpsProxy:
            self._logProxy(httpProxy)
        else:
            if httpProxy:
                self._logProxy(httpProxy)
            if httpsProxy:
                self._logProxy(httpsProxy)

        # Load the top-level proxy configuration.
        generalProxyConfig = FMEGeneralProxyHandler()
        generalProxyConfig.configure(fmeSession)
        self.pac_enabled = generalProxyConfig.use_pac

        # If proxies are configured, or PAC is enabled, and a proxy username specified, then
        # ensure the proxy authentication method is supported.
        enforce_proxy_auth_method = (
            generalProxyConfig.use_pac or generalProxyConfig.proxies
        ) and generalProxyConfig.user
        if enforce_proxy_auth_method and not self._isProxyAuthMethodSupported(
            generalProxyConfig.auth_method
        ):
            raise UnsupportedProxyAuthenticationMethod(
                self.logPrefix, generalProxyConfig.auth_method
            )

        # Configure PyPAC with proxy credentials, if any.
        if generalProxyConfig.user:
            self.proxy_auth = HTTPProxyAuth(generalProxyConfig.user, generalProxyConfig.password)

        # PR70705: Honour system proxy exceptions on Windows.
        if generalProxyConfig.proxies and os.name == "nt":
            configure_proxy_exceptions()

        # PR70807: FME Custom Proxy Map.
        customProxyMap = FMECustomProxyMapHandler()
        customProxyMap.configure(fmeSession)

        return generalProxyConfig, customProxyMap

    def _logProxy(self, proxy_url):
        """Log about a proxy being used."""
        self._log.info(
            kFME_MSGNUM_USING_PROXY,
            self.logPrefix,
            proxy_url_without_credentials(proxy_url),
            extra=_no_prepend_args,
        )

    @staticmethod
    def _isProxyAuthMethodSupported(auth_method):
        """:returns: True if there's no proxy authentication or if it's Basic. NTLM and Digest aren't supported."""
        return not auth_method or auth_method == "basic"

    def request(self, method, url, **kwargs):
        """Make a request. If the request fails due to SSL certificate
        verification failure, a warning is logged, SSL certificate verification
        is disabled for the rest of the session, and the request is retried.

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
        self.requestCount += 1

        # PR62730: Specify a timeout if not already specified, as the default is no timeout.
        if "timeout" not in kwargs:
            kwargs["timeout"] = REQUEST_DEFAULT_TIMEOUT

        # FMEENGINE-63687: Non-proxy hosts.
        if not kwargs.get("proxies"):
            try:
                if self._generalProxyConfig.is_non_proxy_host(urlparse(url).hostname):
                    self._log.debug("Non-Proxy Hosts: Directly accessing '%s'", url)
                    kwargs["proxies"] = REQUESTS_NO_PROXY_CONFIG
            except ValueError:
                pass  # Ignore malformed URLs.

        # PR70807: FME Custom Proxy Map.
        # Only use custom proxy map if caller did not specify any proxies.
        if not kwargs.get("proxies"):
            customProxyForUrl = self._customProxyMap.custom_proxy_for_url(url)
            if customProxyForUrl and not customProxyForUrl.proxy_url:
                self._log.debug("Custom Proxy Map: Directly accessing '%s'", url)
                kwargs["proxies"] = REQUESTS_NO_PROXY_CONFIG
            elif customProxyForUrl:
                self._log.debug(
                    "Custom Proxy Map: Using proxy '%s' for URL '%s'",
                    customProxyForUrl.sanitized_proxy_url,
                    url,
                )
                if not self._isProxyAuthMethodSupported(customProxyForUrl.auth_method):
                    raise UnsupportedProxyAuthenticationMethod(
                        self.logPrefix, customProxyForUrl.auth_method
                    )
                kwargs["proxies"] = {
                    "http": customProxyForUrl.proxy_url,
                    "https": customProxyForUrl.proxy_url,
                }
                # Log about the custom proxy every time it changes to a different proxy.
                if self._lastUsedCustomProxy != customProxyForUrl.sanitized_proxy_url:
                    self._lastUsedCustomProxy = customProxyForUrl.sanitized_proxy_url
                    self._logProxy(customProxyForUrl.sanitized_proxy_url)

        try:
            return super(FMERequestsSession, self).request(method, url, **kwargs)

        except SSLError as e:
            # FME 2021.1+: All the handling below is considered legacy. See FMEDESKTOP-10332.
            if not self._legacy_verify_mode:
                raise
            # FYI: SSLError is a subclass of ConnectionError.
            # There can be some triple-nested SSLError in e.message,
            # so just cut to the chase and cast it to str to get the actual message.
            message = str(e)

            # PR52903: If SSL certificate verification fails, then stop trying to verify certificates.
            # PR57640: After upgrading to Python 2.7.8 (PR54953), need to catch hostname mismatch exception too.
            if "certificate verify failed" in message or "doesn't match" in message:
                try:
                    # Warn about certificate verification failure, and that we're proceeding without it.
                    urlParts = urlparse(url)
                    self._log.warning(
                        kFME_MSGNUM_SSL_CERTIFICATE_VERIFY_FAILED,
                        self.logPrefix,
                        urlParts.netloc,
                        message,
                        extra=_no_prepend_args,
                    )
                except TypeError:
                    pass  # Logger can't handle FME message numbers. Ignore.
                self.verify = False  # This Session shall no longer verify certificates.
                return super(FMERequestsSession, self).request(
                    method, url, **kwargs
                )  # Retry the same request.

            raise  # Not the kind of SSLError handled by this class, so bubble it up.


class HTTPBearerAuth(AuthBase):
    """An authentication object to add to the Requests session.

    This object supplies the OAuth 2.0 access token required for all
    authenticated requests via an HTTP header of the form
    `Authorization: Bearer [token]`.
    """

    def __init__(self, access_token):
        """
        :param str access_token: The access token.
        """
        self.access_token = access_token

    def __call__(self, req):
        req.headers["Authorization"] = "Bearer " + self.access_token
        return req


def get_auth_object(auth_type, user="", password="", format_name=""):
    """Get an appropriately-configured authentication object for use with the
    Requests library.

    :param str auth_type: The type of authentication object to obtain.
       Must be one of: `None`, `Kerberos`, `Basic`, `Digest`, `NTLM`. Case insensitive.
    :param str user: Ignored if not applicable to the specified auth type.
    :param str password: Ignored if not applicable to the specified auth type.
    :param str format_name: Name of format to use if auth_type is `Kerberos`.
    :return: The configured authentication object.
    :rtype: requests.auth.AuthBase or None
    :raises ValueError: if authentication type is unrecognized.
    """
    auth_type = auth_type.upper()
    # These types don't need a username and password.
    if auth_type == "NONE":
        return None
    elif auth_type == "KERBEROS":
        from fmegeneral.kerberos import getRequestsKerberosAuthObject

        return getRequestsKerberosAuthObject(format_name)

    # TODO: Convert to FME message.
    if not user or not password:
        raise ValueError("Authentication type '%s' requires a username and password" % auth_type)

    # These types need a username and password.
    if auth_type == "BASIC":
        from requests.auth import HTTPBasicAuth

        return HTTPBasicAuth(user, password)
    elif auth_type == "DIGEST":
        from requests.auth import HTTPDigestAuth

        return HTTPDigestAuth(user, password)
    elif auth_type == "NTLM":
        from requests_ntlm import HttpNtlmAuth

        return HttpNtlmAuth(user, password)
    else:
        # This should not happen in production, as the GUI should restrict to valid types.
        raise ValueError("Unknown authentication type '%s'" % auth_type)


def proxy_url_without_credentials(proxy_url):
    """Given a proxy URL, return it with any proxy credentials removed.

    :param str proxy_url: The proxy url.
    """
    credentials_separator_index = proxy_url.rfind("@")
    if credentials_separator_index > -1:
        # Strip out credentials if they're present.
        proxy_url = (
            proxy_url[: proxy_url.find("://") + 3] + proxy_url[credentials_separator_index + 1 :]
        )
    return proxy_url


FMEProxyDefinition = namedtuple("FMEProxyDefinition", ["env_var", "proxy_url", "auth_method"])
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
    """Handles parsing of the proxy settings that apply to all requests by
    default.

    :type proxies: list[:class:`FMEProxyDefinition`]
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

    def configure(self, fmeSession):
        """Load general proxy configuration from FME.

        :param FMESession fmeSession: Configuration is loaded from this.
        """
        proxy_config = fmeSession.getProperties(FMESESSION_PROP_NETWORK_PROXY, {})
        use_system_proxy = False
        i = 0
        while i < len(proxy_config):
            key, value = proxy_config[i], proxy_config[i + 1]
            if (
                key in ("http_proxy", "https_proxy", "ftp_proxy")
                and proxy_config[i + 2] == "proxy_auth_method"
            ):
                # Proxy values are not FME-encoded.
                self.proxies.append(FMEProxyDefinition(key, value, proxy_config[i + 3].lower()))
                i += 4
                continue
            if key == "use-system-proxy":
                use_system_proxy = choiceToBool(value)
            if key == "non_proxy_hosts":
                try:
                    for host_regex in json.loads(value):
                        self.non_proxy_hosts.append(re.compile(host_regex, re.I))
                except (json.JSONDecodeError, re.error):
                    warnings.warn("FME non-proxy-hosts: not JSON or bad regex")
            i += 2

        # Use System Proxy plus presence of general proxies probably means a PAC isn't being used.
        # Use System Proxy but no general proxies must mean to find and honour any PAC.
        self.use_pac = use_system_proxy and not self.proxies

        # Grab proxy credentials from Workbench. When a PAC is in use, we need these standalone values.
        proxy_network_config = fmeSession.getProperties(FMESESSION_PROP_NETWORK_PROXY_SETTINGS, {})
        for i in range(0, len(proxy_network_config), 2):
            key, value = proxy_network_config[i], proxy_network_config[i + 1]
            if key == "system-proxy-user":
                self.user = value
            elif key == "system-proxy-password":
                self.password = value
            elif key == "system-proxy-authentication-method":
                self._auth_method = value

    @property
    def auth_method(self):
        """Get the proxy authentication method, either at the system-level
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
        :return: True if the given hostname matches a hostname configured to use no proxy.
        """
        if not host:
            return False
        return any(map(lambda host_re: host_re.match(host), self.non_proxy_hosts))


class FMECustomProxyMapHandler(object):
    """Handles parsing of the FME Custom Proxy Map, which assigns proxies for
    specific URLs.
    """

    # See PR70807.

    def __init__(self):
        self._customProxyMap = []

    def custom_proxy_for_url(self, url):
        """Consult the FME custom proxy map for a proxy configuration to use
        for the given URL. It's up to the caller to handle the proxy
        authentication method.

        :param str url: URL for which to find a custom proxy mapping. Case-insensitive.
        :returns: Custom proxy map entry matching the given URL, or `None` if there's no match.
        :rtype: :class:`FMECustomProxyMap`
        """
        url = url.lower()
        for proxyMap in self._customProxyMap:
            if url.startswith(proxyMap.url):
                return proxyMap
        return None

    def configure(self, fmeSession):
        """Load Custom Proxy Map configuration from FME.

        :param FMESession fmeSession: Configuration is loaded from this.
        """
        proxy_config = fmeSession.getProperties(FMESESSION_PROP_NETWORK_PROXY, {})
        i = 0
        while i < len(proxy_config):
            key, value = proxy_config[i], proxy_config[i + 1]
            if key == "source-url" and proxy_config[i + 2] == "proxy-info":
                self._customProxyMap.append(
                    self.parse_custom_proxy_map(fmeSession, value, proxy_config[i + 3])
                )
                i += 4
                continue
            i += 2

    @staticmethod
    def parse_custom_proxy_map(fmesession, url, proxy_info):
        """Parse a serialized custom proxy map configuration entry from FME.

        :param FMESession fmesession: For decoding FME-encoded strings.
        :param str url: FME-encoded URL for the custom proxy map.
        :param str proxy_info: FME-encoded and comma-delimited proxy configuration for the custom proxy map.
        :rtype: :class:`FMECustomProxyMap`
        """
        url = fmesession.decodeFromFMEParsableText(
            url
        ).lower()  # lower() for case-insensitive comparisons.

        proxy_map_info = stringArrayToDict(proxy_info.split(","))
        proxy_url = fmesession.decodeFromFMEParsableText(proxy_map_info["proxy-url"]).strip()
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
        user = fmesession.decodeFromFMEParsableText(proxy_map_info["user"])
        password = fmesession.decodeFromFMEParsableText(proxy_map_info["password"])
        requires_authentication = choiceToBool(proxy_map_info["requires-authentication"])

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
            proxy_url_with_creds = "{}://{}{}".format(parsed_proxy.scheme, creds, netloc)

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
        :param str log_prefix: The prefix to use for all log messages from this class, e.g. "[format name] [direction]".
        :param str auth_method: Proxy authentication method.
        """
        super(UnsupportedProxyAuthenticationMethod, self).__init__(
            kFME_MSGNUM_PROXY_AUTH_MODE_UNSUPPORTED, [log_prefix, auth_method]
        )


def configure_proxy_exceptions():
    """Set the `NO_PROXY` environment variable based on Windows Internet
    Options. Requests and other Python HTTP libraries should transparently
    honour this environment variable. No-op on non-Windows, or if `NO_PROXY` is
    already set.

    :returns: True if proxy settings were picked up from the Windows Registry
       and the `NO_PROXY` environment variable was set using it.
    :rtype: bool
    """
    if get_env_var(ENV_NO_PROXY) or os.name != "nt":
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

    # Shortcomings: No automatic recognition of what a local address is. No IP range/wildcard support.
    overrides = [entry.strip() for entry in overrides.split(";")]
    no_proxy_entries = list(
        filter(lambda entry: entry not in ("<local>", "<-loopback>"), overrides)
    )
    if len(no_proxy_entries) < len(overrides):
        no_proxy_entries.extend(["localhost", "127.0.0.1", "::1"])
    os.environ[ENV_NO_PROXY] = ", ".join(no_proxy_entries)
    return True


def download_file(response, destination_path):
    """Download a file to the local filesystem. The download is streamed so
    that the whole file doesn't get loaded into memory.

    :param requests.Response response: A response for the file to download, initialized
       with stream=True
    :param str destination_path: Path to destination file.
    :returns: MIME type of the downloaded file.
    """
    with open(destination_path, "wb") as outf:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=1024):
            outf.write(chunk)
