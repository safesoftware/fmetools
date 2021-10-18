import json
import os
import pytest

from fmeobjects import FMESession

from fmetools.fmehttp import (
    FMECustomProxyMapHandler,
    FMEGeneralProxyHandler,
    FMERequestsSession,
    UnsupportedProxyAuthenticationMethod,
    proxy_url_without_credentials,
    get_auth_object,
    _configure_proxy_exceptions,
)
from requests.exceptions import SSLError, ConnectionError

from six.moves.urllib.parse import urlparse

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch


REQUEST_DEFAULT_TIMEOUT = 60  # Assumed from fmehttp


class MockFMESession(FMESession):
    # Python classes from C can't be modified with unittest.mock.
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


def test_reject_unsupported_auth_method():
    mockSession = MockFMESession(mock_proxy_config)
    reqSession = FMERequestsSession("foo", fme_session=mockSession)
    with pytest.raises(UnsupportedProxyAuthenticationMethod):
        reqSession.get("http://google.ca/foo")


def test_empty_proxy_url():
    # This is a valid configuration, meaning to not use a proxy for the given URL.
    proxy_info = "proxy-url,,proxy-port,88,requires-authentication,yes,user,a,password,b,authentication-method,basic"
    assert get_custom_proxy_map(proxy_info).proxy_url == ""


# General proxy config tests


def test_parse():
    mockSession = MockFMESession(mock_proxy_config)
    handler = FMEGeneralProxyHandler()
    handler.configure(mockSession)
    assert 3 == len(handler.proxies)
    assert "" == handler.proxies[0].auth_method
    assert "basic" == handler.proxies[1].auth_method
    assert handler.use_pac is False  # General proxy config present, so don't use PAC.


def test_parse_pac_enabled():
    mockSession = MockFMESession(["use-system-proxy", "yes"])
    handler = FMEGeneralProxyHandler()
    handler.configure(mockSession)
    assert handler.use_pac is True


def test_no_use_system_proxy():
    mockSession = MockFMESession(["use-system-proxy", "no"])
    handler = FMEGeneralProxyHandler()
    handler.configure(mockSession)
    assert handler.use_pac is False


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
def test_request_with_non_proxy_Host(url, expected_value):
    handler = FMEGeneralProxyHandler()
    handler.configure(MockFMESession(mock_proxy_config))
    host = urlparse(url).hostname
    assert handler.is_non_proxy_host(host) is expected_value


def test_reject_unsupported_auth_method():
    # To simplify things, this mock combines settings found in 2 different FME proxy config keys.
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
        FMERequestsSession("foo", fme_session=mockSession)


def test_log_environment_proxies():
    # Coverage only.
    proxy = "http://127.0.0.1:8080"
    env_var_combos = [
        {"http_proxy": proxy, "https_proxy": proxy},
        {"http_proxy": proxy},
        {"https_proxy": proxy},
    ]
    for env_vars in env_var_combos:
        with patch.dict("os.environ", env_vars):
            FMERequestsSession("foo")


# FMERequestSession tests


@pytest.mark.parametrize(
    "expected,input",
    [
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
        ("http://127.0.0.1:8080", "http://foo:bar@127.0.0.1:8080"),
    ],
)
def test_proxy_url_without_credentials(expected, input):
    assert expected == proxy_url_without_credentials(input)


def test_simple_request():
    session = FMERequestsSession(
        "foo", fme_session=MockFMESession([])
    )  # Ensure proxy map is not used.
    session.pac_enabled = False  # Don't go looking for a PAC file.
    with patch("requests.Session.request") as request:
        session.get("http://example.org")
    request.assert_called_once_with(
        "GET",
        "http://example.org",
        timeout=REQUEST_DEFAULT_TIMEOUT,
        proxies=None,
        allow_redirects=True,
    )


def test_request_with_proxy_map():
    session = FMERequestsSession("foo", fme_session=MockFMESession(mock_proxy_config))
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


def test_ssl_fail_reraise():
    session = FMERequestsSession(
        "foo", fme_session=MockFMESession([])
    )  # Ensure proxy map is not used.
    with pytest.raises(SSLError):
        with patch(
            "requests.Session.request",
            side_effect=SSLError("unrecognized error message"),
        ):
            session.get("http://example.org")


# get_auth_object tests


def test_none():
    assert get_auth_object("none") is None


def test_simple_auth_types():
    for auth_method in ("basic", "digest"):
        assert get_auth_object(auth_method, "foo", "bar")


def test_ntlm():
    assert get_auth_object("ntlm", "domain\\user", "bar")
    assert get_auth_object("ntlm", "foo", "bar")
    assert get_auth_object("ntlm")


def test_unrecognized():
    with pytest.raises(ValueError):
        get_auth_object("foo", "foo", "foo")


# system_proxy_exceptions tests


@pytest.mark.skipif(os.name == "nt", reason="on Windows")
def test_non_windows():
    no_proxy = os.environ.pop("no_proxy", None)
    assert _configure_proxy_exceptions() is False
    if no_proxy:
        os.environ["no_proxy"] = no_proxy


@pytest.mark.skipif(os.name != "nt", reason="not Windows")
@pytest.mark.xfail(reason="Machine may not have proxy exceptions defined")
def test_windows():
    no_proxy = os.environ.pop("no_proxy", None)
    assert "no_proxy" not in os.environ
    assert _configure_proxy_exceptions() is True
    no_proxy = os.environ["no_proxy"]
    assert "localhost" in no_proxy
    if no_proxy:
        os.environ["no_proxy"] = no_proxy
