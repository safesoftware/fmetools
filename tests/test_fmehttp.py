# coding: utf-8

import json
import os

import fme
import pytest

from fmeobjects import FMESession
from hypothesis import given, assume
from hypothesis.strategies import none, text, one_of

from fmetools.http import (
    FMECustomProxyMapHandler,
    FMEGeneralProxyHandler,
    FMERequestsSession,
    UnsupportedProxyAuthenticationMethod,
    proxy_url_without_credentials,
    get_auth_object,
    _configure_proxy_exceptions,
)
from requests.exceptions import SSLError

from six.moves.urllib.parse import urlparse

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch  # PY2 backport library


REQUEST_DEFAULT_TIMEOUT = 60  # Assumed from fmehttp


class MockFMESession(FMESession):
    # Superclass can't be modified with unittest.mock.
    def __init__(self, retval):
        super(MockFMESession, self).__init__()
        self.retval = retval

    def getProperties(self, foo, bar):
        return self.retval


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


# Custom proxy map tests


def get_custom_proxy_map(proxy_info):
    return FMECustomProxyMapHandler.parse_custom_proxy_map(
        FMESession(), "http:<solidus><solidus>example.com<solidus>", proxy_info
    )


def test_parse_simple():
    proxy_info = "proxy-url,http:<solidus><solidus>0.0.0.0<solidus>whatever,proxy-port,88,requires-authentication,yes,user,a,password,b,authentication-method,basic"
    mapping = get_custom_proxy_map(proxy_info)
    assert "http://example.com/" == mapping.url
    assert "http://a:b@0.0.0.0:88" == mapping.proxy_url
    assert "http://0.0.0.0:88" == mapping.sanitized_proxy_url
    assert "basic" == mapping.auth_method


def test_have_credentials_but_not_require_auth():
    proxy_info = "proxy-url,http:<solidus><solidus>0.0.0.0<solidus>whatever,proxy-port,80,requires-authentication,no,user,a,password,b,authentication-method,basic"
    mapping = get_custom_proxy_map(proxy_info)
    assert "http://0.0.0.0:80" == mapping.proxy_url
    assert "http://0.0.0.0:80" == mapping.sanitized_proxy_url


def test_credentials_special_chars():
    proxy_info = "proxy-url,http:<solidus><solidus>0.0.0.0<solidus>whatever,proxy-port,80,requires-authentication,yes,user,a<at>a,password,b<at>b,authentication-method,basic"
    mapping = get_custom_proxy_map(proxy_info)
    assert "http://a%40a:b%40b@0.0.0.0:80" == mapping.proxy_url


def test_parse_and_lookup():
    handler = FMECustomProxyMapHandler()
    handler.configure(MockFMESession(mock_proxy_config))
    assert (
        "http://1.1.1.1:80"
        == handler.custom_proxy_for_url("http://google.ca/").sanitized_proxy_url
    )
    assert (
        "http://0.0.0.0:80"
        == handler.custom_proxy_for_url("http://google.ca/FOOZ").sanitized_proxy_url
    )
    assert handler.custom_proxy_for_url("http://example.com") is None


def test_reject_unsupported_auth_method_in_custom_proxy_map():
    mockSession = MockFMESession(mock_proxy_config)
    reqSession = FMERequestsSession(fme_session=mockSession)
    with pytest.raises(UnsupportedProxyAuthenticationMethod):
        reqSession.get("http://google.ca/foo")


def test_empty_proxy_url():
    # This is a valid configuration, meaning to not use a proxy for the given URL.
    proxy_info = "proxy-url,,proxy-port,88,requires-authentication,yes,user,a,password,b,authentication-method,basic"
    assert get_custom_proxy_map(proxy_info).proxy_url == ""


# General proxy config tests


def test_generalproxyhandler_parse():
    mockSession = MockFMESession(mock_proxy_config)
    handler = FMEGeneralProxyHandler()
    handler.configure(mockSession)
    assert 3 == len(handler.proxies)
    assert "" == handler.proxies[0].auth_method
    assert "basic" == handler.proxies[1].auth_method
    assert handler.use_pac is False  # General proxy config present, so don't use PAC.


@pytest.mark.parametrize("value", ["yes", "no"])
def test_generalproxyhandler_use_system_proxy_flag(value):
    mockSession = MockFMESession(["use-system-proxy", value])
    handler = FMEGeneralProxyHandler()
    handler.configure(mockSession)
    assert handler.use_pac == (value is "yes")


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
def test_generalproxyhandler_is_non_proxy_host(url, expected_value):
    handler = FMEGeneralProxyHandler()
    handler.configure(MockFMESession(mock_proxy_config))
    host = urlparse(url).hostname
    assert handler.is_non_proxy_host(host) is expected_value


def test_reject_unsupported_auth_method_in_general_proxy_settings():
    mockSession = MockFMESession(
        [
            "http_proxy",
            "http://127.0.0.1:8888/",
            "proxy_auth_method",
            "ntlm",
            "system-proxy-user",
            "foo",
        ]
    )
    with pytest.raises(UnsupportedProxyAuthenticationMethod):
        FMERequestsSession(fme_session=mockSession)


def test_log_env_proxies():
    # Coverage only.
    proxy = "http://127.0.0.1:8080"
    env_var_combos = [
        {"http_proxy": proxy, "https_proxy": proxy},
        {"http_proxy": proxy},
        {"https_proxy": proxy},
    ]
    for env_vars in env_var_combos:
        with patch.dict("os.environ", env_vars):
            FMERequestsSession()


@pytest.mark.parametrize(
    "expected,proxy_url",
    [
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
        ("http://127.0.0.1:8080", "http://foo:bar@127.0.0.1:8080"),
    ],
)
def test_proxy_url_without_credentials(expected, proxy_url):
    assert expected == proxy_url_without_credentials(proxy_url)


@pytest.fixture
def no_proxy_requests_session():
    # Ensure proxy map is not used.
    session = FMERequestsSession(fme_session=MockFMESession([]))
    session.pac_enabled = False  # Don't go looking for a PAC file.
    return session


def test_mock_request(no_proxy_requests_session):
    with patch("requests.Session.request") as request:
        no_proxy_requests_session.get("http://example.org")
    request.assert_called_once_with(
        "GET",
        "http://example.org",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        proxies=None,
        allow_redirects=True,
    )


@pytest.mark.vcr
def test_live_request(no_proxy_requests_session):
    """
    Make a GET request without mocking.
    """
    resp = no_proxy_requests_session.get("https://httpbin.org/json")
    assert resp.ok
    assert resp.json()
    user_agent = resp.request.headers["User-Agent"]
    assert user_agent.startswith("FME/") and "python-requests/" in user_agent


def test_missing_macrovalues(monkeypatch):
    """
    In older FME, `fme.macroValues` is only defined when FME is running Python.
    Make sure :class:`FMERequestsSession` can still instantiate when it's undefined.
    """
    monkeypatch.delattr(fme, "macroValues", raising=False)
    FMERequestsSession()


def test_mock_request_with_proxy_map():
    session = FMERequestsSession(fme_session=MockFMESession(mock_proxy_config))
    session.pac_enabled = False  # Don't go looking for a PAC file.
    with patch("requests.Session.request") as request:
        session.get("http://google.ca/blah")
    request.assert_called_once_with(
        "GET",
        "http://google.ca/blah",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        allow_redirects=True,
        proxies={"http": "http://1.1.1.1:80", "https": "http://1.1.1.1:80"},
    )
    with patch("requests.Session.request") as request:
        session.get("http://example.org")
    request.assert_called_once_with(
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
    "auth_type", ["none", "BaSiC", "digest", "ntlm", "kerberos", "foo"]
)
@given(user=one_of(text(max_size=1), none()), password=one_of(text(max_size=1), none()))
def test_get_auth_object(auth_type, user, password):
    if auth_type == "foo":
        with pytest.raises(ValueError):
            get_auth_object(auth_type, user, password)
        return
    if auth_type == "ntlm":
        assume(user is not None)
    auth = get_auth_object(auth_type, user, password)
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
    registry_value, expected_no_proxy_value, monkeypatch
):
    if os.name != "nt":
        assert not _configure_proxy_exceptions()
        return

    try:
        import winreg
    except ImportError:
        import _winreg as winreg  # PY2.

    def when_key_not_found(_, __):
        raise WindowsError()

    monkeypatch.delenv("no_proxy", raising=False)

    monkeypatch.setattr(winreg, "QueryValueEx", when_key_not_found)
    assert not _configure_proxy_exceptions()

    try:
        monkeypatch.setattr(
            winreg, "QueryValueEx", lambda _, __: (registry_value, None)
        )
        assert _configure_proxy_exceptions()
        assert os.environ["no_proxy"] == expected_no_proxy_value
        if expected_no_proxy_value:
            assert not _configure_proxy_exceptions()
    finally:
        os.environ.pop("no_proxy", None)  # teardown
