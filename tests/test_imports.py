"""
Import modules that have no tests, just to get coverage reporting.
"""


def test_import_localize():
    from fmetools import localize  # noqa: F401


def test_import_scripted_selection():
    from fmetools import scripted_selection  # noqa: F401


def test_import_webservices():
    from fmetools import webservices  # noqa: F401
