# coding: utf-8

"""
Helpers for enabling localized strings in Python package code via gettext.
"""
import os


def _get_default_locale_dir():
    """
    Return the directory where localization files are stored.
    Assumes that fmetools has been vendorized as a whl according to the fpkg spec.
    """
    return os.path.abspath(__file__ + "/../../../i18n")


def enable_module_localization(
    python_module_name, locale_dir=None, enable_fallback=True, **kwargs
):
    """
    Attempt to load localized messages.
    Uses the default `gettext` behaviour to determine the language.

    :param str python_module_name: Name of the python module to localize e.g. `fmepy_module`
    :param str locale_dir: locale dir to look for .mo files in.
        If not specified, uses :func:`_get_default_locale_dir`
    :param bool enable_fallback:
        Whether to use the original localized strings if a .mo file cannot be found
    :param kwargs: additional keyword arguments to pass to ``gettext.translation()``
    :return: configured gettext
    """
    import gettext

    if not locale_dir:
        locale_dir = _get_default_locale_dir()
    t = gettext.translation(
        python_module_name, locale_dir, fallback=enable_fallback, **kwargs
    )
    tr = t.gettext
    return tr


def enable_module_localization_with_plurals(
    python_module_name, locale_dir=None, enable_fallback=True, **kwargs
):
    """
    Attempt to load localized messages. Supports localized strings which specify plurals.
    Uses the default `gettext` behaviour to determine the language.

    :param str python_module_name: Name of the python module to localize e.g. `fmepy_module`
    :param str locale_dir: locale dir to look for .mo files in. If not specified, uses :func:`_get_default_locale_dir`
    :param bool enable_fallback: Whether to use the original localized strings if a .mo file cannot be found
    :param kwargs: additional keyword arguments to pass to ``gettext.translation()``
    :return: configured gettext and configured ngettext
    """
    import gettext

    if not locale_dir:
        locale_dir = _get_default_locale_dir()
    t = gettext.translation(
        python_module_name, locale_dir, fallback=enable_fallback, **kwargs
    )
    tr = t.gettext
    tr_n = t.ngettext
    return tr, tr_n
