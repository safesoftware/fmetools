# coding: utf-8

"""
Helpers for working with FME Named Connections and FME Web Services.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import six
from fmewebservices import (
    FMENamedConnectionManager,
    FMEBasicConnection,
    FME_HTTP_AUTH_METHOD_BASIC,
    FME_HTTP_AUTH_METHOD_DIGEST,
    FME_HTTP_AUTH_METHOD_NTLM,
    FME_HTTP_AUTH_METHOD_NONE,
    FMEOAuthV2Connection,
    FMETokenConnection,
)
from . import tr
from fmeobjects import FMEException
from requests.auth import AuthBase

from .http import get_auth_object

# 'Dynamic' in Workbench GUI means the auth method is set in
# the Web Connection definition instead of the Web Service definition.
CONN_AUTH_METHOD_TO_KEYWORD = {
    FME_HTTP_AUTH_METHOD_BASIC: "BASIC",
    FME_HTTP_AUTH_METHOD_DIGEST: "DIGEST",
    FME_HTTP_AUTH_METHOD_NTLM: "NTLM",
    FME_HTTP_AUTH_METHOD_NONE: "NONE",
}


class NamedConnectionManager(FMENamedConnectionManager):
    """
    This subclass exists to make superclass methods writeable for unit test
    mocking purposes.
    """

    def __init__(self):
        super(NamedConnectionManager, self).__init__()


class FMETokenConnectionWrapper(object):
    """
    Wrapper around token-based FME Web Connections, to interoperate better
    with Requests.
    """

    def __init__(self, token_connection):
        """
        :type token_connection: FMETokenConnection or FMEOAuthV2Connection
        :param token_connection: The token-based connection to wrap.
        """
        self.wrapped_conn = token_connection

    def get_authorization_header(self):
        """
        Gets the authorization header name and its value.

        :return: Authorization header name, and its value.
            Unlike the original `getAuthorizationHeader()`,
            these values are cleaned up for use with Requests.
            The trailing colon is removed from the header.
            Then both the header and value have leading and trailing spaces stripped,
            as required by `Requests 2.11 <https://github.com/requests/requests/issues/3488>`_.
        :rtype: str, str
        """
        header, value = self.wrapped_conn.getAuthorizationHeader()
        header = header.replace(":", "").strip()
        value = value.strip()
        return header, value

    def get_access_token(self):
        """
        Gets the token value.

        :returns: Token value, stripped of leading and trailing spaces.
        """
        return self.wrapped_conn.getAccessToken().strip()

    def set_suspect_expired(self):
        """
        Set by clients when they received an HTTP 401 response.
        The infrastructure will then always consider the token expired.
        """
        return self.wrapped_conn.setSuspectExpired()

    def get_authorization_param_key(self):
        """
        Gets the query parameter for the token.

        :returns: query parameter name, stripped of leading and trailing spaces.
        """
        param, _ = self.wrapped_conn.getAuthorizationQueryString()
        return param.strip()

    def get_authorization_header_name(self):
        """
        Gets the name of the authorization header for the token.

        :returns: authorization header name, stripped of leading and trailing spaces.
        """
        header, _ = self.get_authorization_header()
        return header

    @property
    def token_in_header(self):
        """
        True if the web connection definition specifies that the token should be placed in the header.

        :rtype: bool
        """
        return self.wrapped_conn.getWebService().supportHeaderAuthorization()

    @property
    def token_in_url(self):
        """
        True if the web connection definition specifies that the token should be placed as a URL query parameter.

        :rtype: bool
        """
        return self.wrapped_conn.getWebService().supportQueryStringAuthorization()


def _create_auth_from_named_connection(conn, client_name=""):
    """
    Get a configured authentication object from a Named Connection
    for use with Requests.

    :param FMENamedConnection conn: The Named Connection / Web Connection object.
    :param str client_name: Name to use for the log message prefix in the failure case,
        e.g. format or transformer name.
    :raises TypeError: If the connection is not a valid Web Connection.
    :rtype: AuthBase
    """
    if isinstance(conn, FMEBasicConnection):
        auth_type = conn.getAuthenticationMethod()
        user, pwd = conn.getUserName(), conn.getPassword()
        return get_auth_object(
            CONN_AUTH_METHOD_TO_KEYWORD[auth_type], user, pwd, client_name
        )
    if isinstance(conn, (FMEOAuthV2Connection, FMETokenConnection)):
        return FMEWebConnectionTokenBasedAuth(FMETokenConnectionWrapper(conn))
    raise TypeError(tr("Unexpected connection type {}").format(repr(conn)))


def set_session_auth_from_named_connection(session, connection_name, client_name):
    """
    Looks up a configured authentication object from a Named Connection and
    set it on a session used for web requests.

    This method handles implementation of the SSL verification setting on Web Connections.

    :param requests.Session|FMERequestsSession session: web session to set the auth on
    :param connection_name: Name of the Named Connection / Web Connection.
        It's an error if no such connection exists.
    :param client_name: Name to use for the log message prefix in the failure case,
        e.g. format or transformer name.
    """
    conn = NamedConnectionManager().getNamedConnection(connection_name)
    if not conn:
        raise NamedConnectionNotFound(client_name, connection_name)

    # this will raise an error if an auth object cannot be successfully created
    session.auth = _create_auth_from_named_connection(conn, client_name)

    session.verify = conn.getVerifySslCertificate()


def get_named_connection_auth(connection_name, client_name):
    """
    Look up a Named Connection and get a configured authentication object
    for use with Requests.

    :param str connection_name: Name of the Named Connection / Web Connection.
        It's an error if no such connection exists.
    :param str client_name: Name to use for the log message prefix in the failure case,
        e.g. format or transformer name.
    :raises NamedConnectionNotFound: If connection does not exist.
    :rtype: AuthBase
    """
    conn = NamedConnectionManager().getNamedConnection(connection_name)
    if not conn:
        raise NamedConnectionNotFound(client_name, connection_name)

    return _create_auth_from_named_connection(conn, client_name)


class FMEWebConnectionTokenBasedAuth(AuthBase):
    """
    A Requests authentication handler that authenticates using tokens
    obtained from FME Web Service Connections.

    These tokens are either arbitrary tokens, or OAuth 2.0 access tokens.
    """

    def __init__(self, wrapped_conn):
        """
        :param FMETokenConnectionWrapper wrapped_conn:
            Wrapped OAuth 2.0 or token-based connection from which to obtain tokens.
        """
        self.conn = wrapped_conn
        self.token_location = None
        self.header_location = None

        # use the web connection definition and honour token placement settings
        if self.conn.token_in_url:
            # Query string parameter name for the token
            self.token_location = self.conn.get_authorization_param_key()

        if self.conn.token_in_header:
            # Header name for the token
            # For OAuth 2.0 connections, this should default to 'Authorization'
            self.header_location = self.conn.get_authorization_header_name()

        assert self.header_location or self.token_location

    def __call__(self, prepared_request):
        _, header_value = self.conn.get_authorization_header()

        if self.token_location:
            # Include token in GET parameters. `params` is not available in `preparedRequest`.
            prepared_request.prepare_url(
                prepared_request.url,
                {self.token_location: self.conn.get_access_token()},
            )

        if self.header_location:
            # Key must be bytestring on PY27.
            # Unicode key on PY27 will cause UnicodeDecodeError in httplib when body is binary.
            header = (
                self.header_location.encode("ascii")
                if six.PY2
                else self.header_location
            )
            prepared_request.headers[header] = header_value

        return prepared_request

    def set_suspect_expired(self):
        """
        Call this method to inform the FME infrastructure that the token may be expired.
        The infrastructure will attempt to get a new token the next time a token is
        requested.
        """
        self.conn.set_suspect_expired()


class NamedConnectionNotFound(FMEException):
    """
    Exception raised when a named connection doesn't exist with the given name.
    """

    def __init__(self, client_name, connection_name):
        base_message = tr(
            "%s: Connection '%s' does not exist."
            + "Check connection parameter and connection definitions in FME options and try again"
        )
        message = base_message % (client_name, connection_name)
        super(NamedConnectionNotFound, self).__init__(message)
