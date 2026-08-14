# coding: utf-8
"""
Tests for ``fmetools.http``, a module that expects ``fmeobjects`` to be present,
but must also remain importable and functional when it's not present.

This test module doesn't import ``fmetools.http`` directly, but provides it via the ``http_module`` fixture.
This allows all tests to be parameterized to cover the cases of ``fmeobjects`` being available or unavailable.
"""

from __future__ import annotations

import builtins
import importlib
import json
import os
import sys
import types
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis.strategies import none, one_of, text
from requests.exceptions import SSLError

REQUEST_DEFAULT_TIMEOUT = 60  # Assumed from fmehttp

FMESESSION_PROP_NETWORK_PROXY = "fme_session_prop_network_proxy"
FMESESSION_PROP_NETWORK_PROXY_SETTINGS = "fme_session_prop_network_proxy_settings"

FME_PARSABLE_TEXT_REPLACEMENTS = {
    "<apos>": "'",
    "<dollar>": "$",
    "<openbracket>": "[",
    "<semicolon>": ";",
    "<solidus>": "/",
    "<space>": " ",
}

try:
    import fme as REAL_FME_MODULE
    import fmeobjects as REAL_FMEOBJECTS_MODULE
except ModuleNotFoundError:
    REAL_FME_MODULE = None
    REAL_FMEOBJECTS_MODULE = None

HttpModule = Any


def decode_fme_parsable_text(value: str) -> str:
    for token, replacement in FME_PARSABLE_TEXT_REPLACEMENTS.items():
        value = value.replace(token, replacement)
    return value


def assert_request_called_once_with(mock_request, method, url, **expected_kwargs):
    """
    Assert that the patched ``requests.Session.request`` was called once with the
    given method, URL, and (at least) the expected keyword arguments.

    Extra keyword arguments are tolerated so the assertion stays robust against
    upstream libraries (e.g. ``pypac``) adding pass-through kwargs like ``params``.
    """
    mock_request.assert_called_once()
    call = mock_request.call_args
    assert call.args == (method, url)
    for key, value in expected_kwargs.items():
        assert call.kwargs[key] == value, (
            f"kwarg {key!r}: expected {value!r}, got {call.kwargs.get(key)!r}"
        )


def make_fake_fme_module(*, has_macrovalues: bool = True) -> types.ModuleType:
    module = types.ModuleType("fme")
    if has_macrovalues:
        module.macroValues = {}
    return module


def import_http_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fmeobjects_available: bool,
    fme_has_macrovalues: bool = True,
) -> HttpModule:
    # In Python 3.9, mock.patch resolves targets via getattr(package, submodule)
    # rather than sys.modules. Reimporting submodules updates the package attribute
    # but monkeypatch.delitem only restores sys.modules, leaving a stale reference.
    # Save and restore submodule attributes on the fmetools package explicitly.
    import fmetools as _fmetools_pkg

    for _attr in ("http", "logfile"):
        if hasattr(_fmetools_pkg, _attr):
            monkeypatch.setattr(_fmetools_pkg, _attr, getattr(_fmetools_pkg, _attr))

    monkeypatch.delitem(sys.modules, "fme", raising=False)
    monkeypatch.delitem(sys.modules, "fmeobjects", raising=False)
    monkeypatch.delitem(sys.modules, "fmetools.http", raising=False)
    monkeypatch.delitem(sys.modules, "fmetools.logfile", raising=False)

    if fmeobjects_available:
        if REAL_FME_MODULE is None or REAL_FMEOBJECTS_MODULE is None:
            pytest.skip("Real fmeobjects is not importable in this test environment")
        if fme_has_macrovalues:
            monkeypatch.setitem(sys.modules, "fme", REAL_FME_MODULE)
        monkeypatch.setitem(sys.modules, "fmeobjects", REAL_FMEOBJECTS_MODULE)
    else:
        monkeypatch.setitem(
            sys.modules,
            "fme",
            make_fake_fme_module(has_macrovalues=fme_has_macrovalues),
        )
        original_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "fmeobjects":
                raise ModuleNotFoundError(
                    "No module named 'fmeobjects'", name="fmeobjects"
                )
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", blocked_import)

    return cast(HttpModule, importlib.import_module("fmetools.http"))


@dataclass
class HttpImportState:
    module: HttpModule
    fmeobjects_available: bool


class MockFMESession:
    def __init__(
        self, general: list[str] | None = None, settings: list[str] | None = None
    ) -> None:
        self.general = list(general or [])
        self.settings = list(settings or [])

    def getProperties(self, propertyCategory: str, properties: Any) -> list[str]:
        if propertyCategory == FMESESSION_PROP_NETWORK_PROXY:
            return self.general
        if propertyCategory == FMESESSION_PROP_NETWORK_PROXY_SETTINGS:
            return self.settings
        raise ValueError(propertyCategory)

    def decodeFromFMEParsableText(self, parsableText: str) -> str:
        return decode_fme_parsable_text(parsableText)


mock_proxy_config = [
    "use-system-proxy",
    "yes",
    "http_proxy",
    "http://127.0.0.1:8888/",
    "proxy_auth_method",
    "",
    "https_proxy",
    "http://127.0.0.1:8888/",
    "proxy_auth_method",
    "basic",
    "ftp_proxy",
    "http://127.0.0.1:8888/",
    "proxy_auth_method",
    "",
    "non_proxy_hosts",
    json.dumps(["localhost", "127\\.0\\.0\\.1", "::1", ".*?\\.base\\.safe\\.com"]),
    "source-url",
    "http:<solidus><solidus>google.ca<solidus>foo",
    "proxy-info",
    "proxy-url,http:<solidus><solidus>0.0.0.0,proxy-port,80,requires-authentication,yes,user,a,password,b,authentication-method,ntlm",
    "source-url",
    "http:<solidus><solidus>google.ca<solidus>",
    "proxy-info",
    "proxy-url,http:<solidus><solidus>1.1.1.1,proxy-port,80,requires-authentication,no,user,a,password,b,authentication-method,basic",
]

mock_proxy_settings = [
    "system-proxy-user",
    "proxy-user",
    "system-proxy-password",
    "proxy-pass",
    "system-proxy-authentication-method",
    "basic",
]


@pytest.fixture(autouse=True, params=[True, False], ids=["fmeobjects", "no_fmeobjects"])
def http_import_state(request, monkeypatch):
    return HttpImportState(
        module=import_http_module(
            monkeypatch, fmeobjects_available=request.param, fme_has_macrovalues=True
        ),
        fmeobjects_available=request.param,
    )


@pytest.fixture
def http_module(http_import_state):
    return http_import_state.module


def get_custom_proxy_map(http_module: HttpModule, proxy_info: str) -> Any:
    return http_module.FMECustomProxyMapHandler.parse_custom_proxy_map(
        MockFMESession(),
        "http:<solidus><solidus>example.com<solidus>",
        proxy_info,
    )


@pytest.fixture
def no_proxy_requests_session(http_module):
    # Ensure proxy map is not used.
    session = http_module.FMERequestsSession(fme_session=MockFMESession())
    session.pac_enabled = False  # Don't go looking for a PAC file.
    return session


def test_import_fallbacks_match_fmeobjects_availability(http_import_state):
    http_module = http_import_state.module

    if http_import_state.fmeobjects_available:
        assert http_module.FMESession is not None
        assert http_module._USER_AGENT.startswith("FME/")
        assert (
            http_module.get_configured_logger("test").__class__.__name__
            == "LoggerAdapter"
        )
    else:
        assert http_module.FMESession is None
        assert http_module._USER_AGENT == ""
        assert http_module.get_configured_logger("test").__class__.__name__ == "Logger"
        assert issubclass(http_module.FMEException, Exception)


def test_proxy_config_from_fme_session_depends_on_fmeobjects(http_import_state):
    http_module = http_import_state.module
    explicit_session = MockFMESession(["use-system-proxy", "no"], mock_proxy_settings)

    proxy_config = http_module.FMEProxyConfig.from_fme_session(explicit_session)
    assert proxy_config.general == ["use-system-proxy", "no"]
    assert proxy_config.settings == mock_proxy_settings

    if http_import_state.fmeobjects_available:
        real_fme_session = http_module.FMESession()
        default_proxy_config = http_module.FMEProxyConfig.from_fme_session()
        assert default_proxy_config.general == real_fme_session.getProperties(
            FMESESSION_PROP_NETWORK_PROXY, []
        )
        assert default_proxy_config.settings == real_fme_session.getProperties(
            FMESESSION_PROP_NETWORK_PROXY_SETTINGS, []
        )
    else:
        with pytest.raises(ValueError, match="FMESession is not available"):
            http_module.FMEProxyConfig.from_fme_session()


def test_proxy_config_from_fme_session_without_arg_fails_without_fmeobjects(
    http_import_state,
):
    if http_import_state.fmeobjects_available:
        pytest.skip("Only applies when fmeobjects is unavailable")

    with pytest.raises(ValueError, match="FMESession is not available"):
        http_import_state.module.FMEProxyConfig.from_fme_session()


def test_requests_session_without_explicit_fme_session_depends_on_fmeobjects(
    http_import_state,
):
    http_module = http_import_state.module

    session = http_module.FMERequestsSession()

    if http_import_state.fmeobjects_available:
        assert session.headers["User-Agent"].startswith("FME/")
    else:
        assert "python-requests/" in session.headers["User-Agent"]
        assert not session.headers["User-Agent"].startswith("FME/")
        assert session._fme_proxy_resolver.general.proxies == []
        assert session._fme_proxy_resolver.general.user == ""
        assert session._fme_proxy_resolver.general.password == ""


def test_requests_session_uses_empty_proxy_config_without_fmeobjects(
    http_import_state,
):
    if http_import_state.fmeobjects_available:
        pytest.skip("Only applies when fmeobjects is unavailable")

    session = http_import_state.module.FMERequestsSession()

    assert session._fme_proxy_resolver.general.proxies == []
    assert session._fme_proxy_resolver.general.user == ""
    assert session._fme_proxy_resolver.general.password == ""
    assert session.pac_enabled is False


def test_requests_session_accepts_real_fmesession_when_fmeobjects_available(
    http_import_state,
):
    if not http_import_state.fmeobjects_available:
        pytest.skip("Only applies when fmeobjects is available")

    http_module = http_import_state.module
    real_fme_session = http_module.FMESession()
    session = http_module.FMERequestsSession(fme_session=real_fme_session)

    assert http_module.FMESession is not None
    assert isinstance(real_fme_session, http_module.FMESession)
    assert session.headers["User-Agent"].startswith(http_module._USER_AGENT)
    assert session._fme_proxy_resolver.general is not None


def test_requests_session_accepts_proxy_config_when_fmesession_unavailable(
    http_import_state,
):
    if http_import_state.fmeobjects_available:
        pytest.skip("Only applies when fmeobjects is unavailable")

    http_module = http_import_state.module
    proxy_config = http_module.FMEProxyConfig(
        general=["use-system-proxy", "no"],
        settings=mock_proxy_settings,
    )
    session = http_module.FMERequestsSession(fme_session=proxy_config)

    assert "python-requests/" in session.headers["User-Agent"]
    assert not session.headers["User-Agent"].startswith("FME/")
    assert session._fme_proxy_resolver.general.user == "proxy-user"
    assert session._fme_proxy_resolver.general.password == "proxy-pass"


def test_requests_session_accepts_empty_proxy_config(http_module):
    session = http_module.FMERequestsSession(
        fme_session=http_module.FMEProxyConfig(general=[], settings=[])
    )

    assert session._fme_proxy_resolver.general.proxies == []
    assert session._fme_proxy_resolver.general.user == ""
    assert session._fme_proxy_resolver.general.password == ""
    assert session.pac_enabled is False


# Custom proxy map tests


@pytest.mark.parametrize(
    "proxy_info,expected_map",
    [
        pytest.param(
            "proxy-url,http:<solidus><solidus>0.0.0.0<solidus>whatever,proxy-port,88,requires-authentication,yes,user,a,password,b,authentication-method,basic",
            (
                "http://example.com/",
                "http://a:b@0.0.0.0:88",
                "http://0.0.0.0:88",
                True,
                "a",
                "b",
                "basic",
            ),
            id="simple_basic_auth",
        ),
        pytest.param(
            "proxy-url,http:<solidus><solidus>0.0.0.0<solidus>whatever,proxy-port,88,requires-authentication,no,user,a,password,b,authentication-method,basic",
            (
                "http://example.com/",
                "http://0.0.0.0:88",
                "http://0.0.0.0:88",
                False,
                "a",
                "b",
                "basic",
            ),
            id="have_creds_but_auth_off",
        ),
        pytest.param(
            "proxy-url,http:<solidus><solidus>0.0.0.0<solidus>whatever,proxy-port,88,requires-authentication,yes,user,Aa0<apos><openbracket><semicolon>!g*<dollar>`<solidus><space>+X,password,Aa0<apos><openbracket><semicolon>!g*<dollar>`<solidus><space>+X,authentication-method,basic",
            (
                "http://example.com/",
                "http://Aa0%27%5B%3B%21g%2A%24%60%2F%20%2BX:Aa0%27%5B%3B%21g%2A%24%60%2F%20%2BX@0.0.0.0:88",
                "http://0.0.0.0:88",
                True,
                "Aa0'[;!g*$`/ +X",
                "Aa0'[;!g*$`/ +X",
                "basic",
            ),
            id="special_chars",
        ),
        pytest.param(
            "proxy-url,,proxy-port,88,requires-authentication,yes,user,a,password,b,authentication-method,basic",
            (
                "http://example.com/",
                "",
                "",
                False,
                "",
                "",
                "",
            ),
            id="empty",  # Valid configuration meaning direct access for the URL.
        ),
    ],
)
def test_parse_custom_proxy_map(http_module, proxy_info, expected_map):
    mapping = get_custom_proxy_map(http_module, proxy_info)
    assert mapping == http_module.FMECustomProxyMap(*expected_map)


def test_parse_and_lookup(http_module):
    handler = http_module.FMECustomProxyMapHandler()
    handler.configure(MockFMESession(mock_proxy_config, mock_proxy_settings))
    assert (
        "http://1.1.1.1:80"
        == handler.custom_proxy_for_url("http://google.ca/").sanitized_proxy_url
    )
    assert (
        "http://0.0.0.0:80"
        == handler.custom_proxy_for_url("http://google.ca/FOOZ").sanitized_proxy_url
    )
    assert handler.custom_proxy_for_url("http://example.com") is None


def test_reject_unsupported_auth_method_in_custom_proxy_map(http_module):
    session = http_module.FMERequestsSession(
        fme_session=MockFMESession(mock_proxy_config, mock_proxy_settings)
    )
    with pytest.raises(http_module.UnsupportedProxyAuthenticationMethod):
        session.get("http://google.ca/foo")


# General proxy config tests


def test_generalproxyhandler_parse(http_module):
    handler = http_module.FMEGeneralProxyHandler()
    handler.configure(MockFMESession(mock_proxy_config, mock_proxy_settings))
    assert len(handler.proxies) == 3
    assert handler.proxies[0].auth_method == ""
    assert handler.proxies[1].auth_method == "basic"
    assert handler.use_pac is False  # General proxy config present, so don't use PAC.
    assert handler.user == "proxy-user"
    assert handler.password == "proxy-pass"
    assert handler.auth_method == "basic"


@pytest.mark.parametrize("value", ["yes", "no"])
def test_generalproxyhandler_use_system_proxy_flag(http_module, value):
    handler = http_module.FMEGeneralProxyHandler()
    handler.configure(MockFMESession(["use-system-proxy", value]))
    assert handler.use_pac == (value == "yes")


@pytest.mark.parametrize(
    "url, expected_value",
    [
        ("https://LoCaLhOsT", True),
        ("https://127.0.0.1:8080", True),
        ("https://foobar.base.safe.com/test", True),
        ("https://[::1]:8080", True),
        ("https://::1:8080", False),  # Intentionally invalid. IPv6 hosts need brackets.
        ("https://example.com", False),
    ],
)
def test_generalproxyhandler_is_non_proxy_host(http_module, url, expected_value):
    handler = http_module.FMEGeneralProxyHandler()
    handler.configure(MockFMESession(mock_proxy_config))
    host = urlparse(url).hostname
    assert handler.is_non_proxy_host(host) is expected_value


def test_reject_unsupported_auth_method_in_general_proxy_settings(http_module):
    mock_session = MockFMESession(
        [
            "http_proxy",
            "http://127.0.0.1:8888/",
            "proxy_auth_method",
            "basic",
        ],
        [
            "system-proxy-user",
            "foo",
            "system-proxy-authentication-method",
            "ntlm",
        ],
    )
    with pytest.raises(http_module.UnsupportedProxyAuthenticationMethod):
        http_module.FMERequestsSession(fme_session=mock_session)


def test_log_env_proxies(http_module):
    # Coverage only.
    proxy = "http://127.0.0.1:8080"
    env_var_combos = [
        {"http_proxy": proxy, "https_proxy": proxy},
        {"http_proxy": proxy},
        {"https_proxy": proxy},
    ]
    for env_vars in env_var_combos:
        with patch.dict("os.environ", env_vars):
            http_module.FMERequestsSession(fme_session=MockFMESession())


@pytest.mark.parametrize(
    "expected,proxy_url",
    [
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
        ("http://127.0.0.1:8080", "http://foo:bar@127.0.0.1:8080"),
    ],
)
def test_proxy_url_without_credentials(http_module, expected, proxy_url):
    assert expected == http_module.proxy_url_without_credentials(proxy_url)


def test_mock_request(no_proxy_requests_session):
    with patch("requests.Session.request") as request:
        no_proxy_requests_session.get("http://example.org")
    assert_request_called_once_with(
        request,
        "GET",
        "http://example.org",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        proxies=None,
        allow_redirects=True,
    )


def test_mock_request_with_pac_enabled_but_no_pac_found(http_module):
    """
    PAC is enabled, but PAC discovery finds nothing.
    """
    session = http_module.FMERequestsSession(
        fme_session=MockFMESession(["use-system-proxy", "yes"])
    )
    assert session.pac_enabled is True  # Use System Proxy with no general proxies.

    with patch("pypac.api.get_pac", return_value=None) as get_pac:
        with patch("requests.Session.request") as request:
            session.get("http://example.org")
    get_pac.assert_called_once()
    assert_request_called_once_with(
        request,
        "GET",
        "http://example.org",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        proxies=None,
        allow_redirects=True,
    )
    # PACSession's own resolver stays unset, since no PAC file was found.
    assert session._proxy_resolver is None
    assert isinstance(session._fme_proxy_resolver, http_module.FMEProxyResolver)


def test_mock_request_with_pac_enabled_and_pac_found(http_module):
    """
    PAC is enabled and a PAC file is found, so ``PACSession`` populates its own
    ``_proxy_resolver``. :class:`FMERequestsSession` must keep resolving FME proxy
    rules from its own resolver on every request, including after PAC discovery.
    """
    from pypac.parser import PACFile

    pac = PACFile("function FindProxyForURL(url, host) { return 'DIRECT'; }")
    session = http_module.FMERequestsSession(
        fme_session=MockFMESession(["use-system-proxy", "yes"])
    )
    with patch("pypac.api.get_pac", return_value=pac):
        with patch("requests.Session.request"):
            session.get("http://example.org")
            session.get("http://example.org")  # PAC resolver now in place.
    assert session.request_count == 2
    assert isinstance(session._fme_proxy_resolver, http_module.FMEProxyResolver)


@pytest.mark.vcr("test_live_request.yaml")
def test_live_request(no_proxy_requests_session, http_import_state):
    """
    Make a GET request without mocking.
    """
    response = no_proxy_requests_session.get("https://httpbin.org/json")
    assert response.ok
    assert response.json()
    user_agent = response.request.headers["User-Agent"]
    assert "python-requests/" in user_agent
    if http_import_state.fmeobjects_available:
        assert user_agent.startswith("FME/")
    else:
        assert not user_agent.startswith("FME/")


def test_missing_macrovalues(http_import_state, monkeypatch):
    """
    In older FME, `fme.macroValues` is only defined when FME is running Python.
    Make sure :class:`FMERequestsSession` can still instantiate when it's undefined.
    """
    del http_import_state
    fme_module = cast(Any, sys.modules["fme"])
    monkeypatch.delattr(fme_module, "macroValues", raising=False)
    http_module = cast(HttpModule, sys.modules["fmetools.http"])
    http_module.FMERequestsSession(fme_session=MockFMESession())


def test_mock_request_with_proxy_map(http_module):
    session = http_module.FMERequestsSession(
        fme_session=MockFMESession(mock_proxy_config, mock_proxy_settings)
    )
    session.pac_enabled = False  # Don't go looking for a PAC file.
    with patch("requests.Session.request") as request:
        session.get("http://google.ca/blah")
    assert_request_called_once_with(
        request,
        "GET",
        "http://google.ca/blah",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        allow_redirects=True,
        proxies={"http": "http://1.1.1.1:80", "https": "http://1.1.1.1:80"},
    )
    with patch("requests.Session.request") as request:
        session.get("http://example.org")
    assert_request_called_once_with(
        request,
        "GET",
        "http://example.org",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        proxies=None,
        allow_redirects=True,
    )


def test_ssl_fail_reraise(no_proxy_requests_session):
    with pytest.raises(SSLError):
        with patch(
            "requests.Session.request",
            side_effect=SSLError("unrecognized error message"),
        ):
            no_proxy_requests_session.get("http://example.org")


@pytest.mark.parametrize(
    "url,verify,expected_exc",
    [
        ("http://google.ca", True, None),
        ("https://google.ca", True, None),
        ("https://google.ca", "", None),
        ("https://google.ca", False, None),
        ("https://self-signed.badssl.com/", True, SSLError),
        ("https://self-signed.badssl.com/", False, None),
        ("https://untrusted-root.badssl.com/", False, None),
    ],
)
def test_SystemCertStoreAdapter(http_module, url, verify, expected_exc):
    """
    Verify that SystemCertStoreAdapter works with a variety of URLs and verify settings.
    """
    session = http_module.FMERequestsSession(fme_session=MockFMESession())
    if expected_exc:
        with pytest.raises(expected_exc):
            session.get(url, verify=verify)
    else:
        session.get(url, verify=verify)


def test_SystemCertStoreAdapter_verify_not_persistent(http_module):
    """
    Ensure that disabling verification doesn't persist and
    disable hostname verification in later requests.
    """
    session = http_module.FMERequestsSession(fme_session=MockFMESession())
    session.get("https://wrong.host.badssl.com/", verify=False)
    with pytest.raises(SSLError) as error:
        session.get("https://wrong.host.badssl.com/")
    assert "hostname mismatch" in str(error.value).lower()


@pytest.mark.parametrize(
    "auth_type", ["none", "BaSiC", "digest", "ntlm", "kerberos", "foo"]
)
@given(user=one_of(text(max_size=1), none()), password=one_of(text(max_size=1), none()))
@settings(
    deadline=5000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)  # often exceeds default 200ms on tox
def test_get_auth_object(http_module, auth_type, user, password):
    if auth_type == "foo":
        with pytest.raises(ValueError):
            http_module.get_auth_object(auth_type, user, password)
        return

    patched_modules = {}
    if auth_type == "ntlm":
        assume(user is not None)
        requests_ntlm = types.ModuleType("requests_ntlm")

        class HttpNtlmAuth:
            def __init__(self, username, secret):
                self.username = username
                self.secret = secret

        requests_ntlm.HttpNtlmAuth = HttpNtlmAuth
        patched_modules["requests_ntlm"] = requests_ntlm

    if auth_type == "kerberos":
        requests_kerberos = types.ModuleType("requests_kerberos")

        class HTTPKerberosAuth:
            def __init__(self, *, mutual_authentication):
                self.mutual_authentication = mutual_authentication

        requests_kerberos.DISABLED = object()
        requests_kerberos.HTTPKerberosAuth = HTTPKerberosAuth
        patched_modules["requests_kerberos"] = requests_kerberos

    with patch.dict(sys.modules, patched_modules):
        auth = http_module.get_auth_object(auth_type, user, password)
    if auth_type == "none":
        assert auth is None
    else:
        assert auth


@pytest.mark.parametrize(
    "registry_value, expected_no_proxy_value",
    [
        ("", ""),
        ("1.1.1.1", "1.1.1.1"),
        ("1.1.1.1; <local>", "1.1.1.1, localhost, 127.0.0.1, ::1"),
        ("1.1.1.1; <local>; <-loopback>", "1.1.1.1, localhost, 127.0.0.1, ::1"),
        ("<local>", "localhost, 127.0.0.1, ::1"),
    ],
)
def test_configure_proxy_exceptions(
    http_module, registry_value, expected_no_proxy_value, monkeypatch
):
    if os.name != "nt":
        assert not http_module._configure_proxy_exceptions()
        return

    import winreg

    def when_key_not_found(_: Any, __: Any) -> None:
        raise OSError()

    monkeypatch.delenv("no_proxy", raising=False)

    monkeypatch.setattr(winreg, "QueryValueEx", when_key_not_found)
    assert not http_module._configure_proxy_exceptions()

    try:
        monkeypatch.setattr(
            winreg, "QueryValueEx", lambda _, __: (registry_value, None)
        )
        assert http_module._configure_proxy_exceptions()
        assert os.environ["no_proxy"] == expected_no_proxy_value
        if expected_no_proxy_value:
            assert not http_module._configure_proxy_exceptions()
    finally:
        os.environ.pop("no_proxy", None)  # teardown
