"""
This module abstracts away concerns for whether we support Kerberos
authentication on the current platform.

requests-kerberos provides Kerberos authentication for the Requests library.
Its dependency for the underlying Kerberos client implementation varies depending on the platform.
Its dependencies are all C extensions.

On Windows:
   WinKerberos is the dependency. We ship this with FME.

On Mac/Linux:
   `kerberos` is the dependency, in particular, PyKerberos. PyKerberos is a fork of Apple Kerberos.
   Both PyKerberos and Apple Kerberos claim the `kerberos` module namespace, and installing one after the other
   will silently clobber the existing library. Some users have preferences for one over the other.
   We don't ship either of these with FME, nor do we specify them as a dependency.
   We use the system Python on these platforms, and don't want to risk clobbering the user's libraries.
   If `kerberos` is importable because it happens to be on the system, then Kerberos auth for Python will be available.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from fmeobjects import FMEException


class KerberosUnsupportedException(FMEException):
    """For use in :func:`getRequestsKerberosAuthObject`."""
    def __init__(self, formatName):
        """
      :param str formatName: Name of format to use in the log message.
      """
        super(KerberosUnsupportedException, self).__init__(
            926851, [formatName])


def getRequestsKerberosAuthObject(formatName):
    """Try to get a Kerberos authentication object to use with :mod:`requests`. Raises
    a user-friendly exception if dependencies couldn't be loaded.

    :param str formatName: Name of format to use in log message if Kerberos is unsupported.
    :return: `requests_kerberos.HTTPKerberosAuth <https://pypi.org/project/requests-kerberos/>`_
    :raises KerberosUnsupportedException: if an ImportError occurred when trying to import requests_kerberos.
       This is most likely because the `kerberos` module isn't available.
    """
    try:
        import requests_kerberos as rk
        # PR78426: Disable mutual auth to work with some customer configs.
        return rk.HTTPKerberosAuth(mutual_authentication=rk.DISABLED, )
    except ImportError:
        raise KerberosUnsupportedException(formatName)
