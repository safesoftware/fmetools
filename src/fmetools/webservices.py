"""
Helpers for working with FME Named Connections and Web Service
Connections.
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

from fmeobjects import FMEException
from requests.auth import AuthBase

from fmetools.fmehttp import get_auth_object

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
    if isinstance(conn, FMEBasicConnection):
        auth_type = conn.getAuthenticationMethod()
        user, pwd = conn.getUserName(), conn.getPassword()
        return get_auth_object(
            CONN_AUTH_METHOD_TO_KEYWORD[auth_type], user, pwd, client_name
        )
    if isinstance(conn, (FMEOAuthV2Connection, FMETokenConnection)):
        return FMEWebConnectionTokenBasedAuth(FMETokenConnectionWrapper(conn))
    raise TypeError("Unexpected connection type {}".format(repr(conn)))


class FMEWebConnectionTokenBasedAuth(AuthBase):
    """
    A Requests authentication handler that authenticates using tokens
    obtained from FME Web Service Connections.

    These tokens are either arbitrary tokens, or OAuth 2.0 access
    tokens.
    """

    def __init__(self, wrapped_conn, token_location=None, header_and_url=False):
        """
        :param FMETokenConnectionWrapper wrapped_conn:
            Wrapped OAuth 2.0 or token-based connection from which to obtain tokens.
        :param str token_location: If None, the token is treated as an
            OAuth 2.0 access token and put in the header.
            Otherwise, this is the query string parameter name for the token.
        :param bool header_and_url: If true, then assume token is an OAuth 2.0 token,
            but include it in both the Authorization header and token_location.
            This is intended for use by ArcGIS Online only.
        """
        assert (header_and_url and token_location) or not header_and_url
        self.conn = wrapped_conn
        self.token_location = token_location
        self.header_and_url = header_and_url

    def __call__(self, prepared_request):
        header, value = self.conn.get_authorization_header()
        # TODO: Remove token_location argument and get it from connection settings.
        # TODO: Remove header_and_url argument and have AGOL implement it.

        if self.token_location:
            # Include token in GET parameters. `params` is not available in `preparedRequest`.
            prepared_request.prepare_url(
                prepared_request.url,
                {self.token_location: self.conn.get_access_token()},
            )
        if not self.token_location or self.header_and_url:
            # Key must be bytestring on PY27.
            # Unicode key on PY27 will cause UnicodeDecodeError in httplib when body is binary.
            if six.PY2:
                header = header.encode("ascii")
            prepared_request.headers[header] = value

        return prepared_request

    def set_suspect_expired(self):
        """
        Set by clients when they received a 401 call failure. The infrastructure
        will then always consider the token expired.
        """
        self.conn.set_suspect_expired()


class NamedConnectionNotFound(FMEException):
    """
    Exception raised when a named connection doesn't exist with the given name.
    """

    def __init__(self, client_name, connection_name):
        super(NamedConnectionNotFound, self).__init__(
            926882, [client_name, connection_name]
        )
