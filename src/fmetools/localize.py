# coding: utf-8
"""
Helpers for enabling localized strings using the :mod:`gettext` module.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

# Nothing here is intended for general use.
__all__ = []


def _get_default_locale_dir():
    """
    Return the directory where localization files are stored.
    Assumes that fmetools has been vendorized as a whl according to the fpkg spec.
    """
    return os.path.abspath(__file__ + "/../../../i18n")


def enable_module_localization(
    python_module_name: str,
    locale_dir: Optional[str] = None,
    enable_fallback: bool = True,
    **kwargs,
) -> Callable:
    """
    Attempt to load localized messages.
    Uses the default :mod:`gettext` behaviour to determine the language.

    :param python_module_name:
        Name of the python module to localize. For instance, ``fmepy_module``.
    :param locale_dir: Folder to look for .mo files in.
        If not specified, uses :func:`_get_default_locale_dir`.
    :param enable_fallback:
        Whether to use the original localized strings if a .mo file cannot be found.
    :param kwargs: Keyword arguments to pass to :func:`gettext.translation`.
    :return: Configured :meth:`gettext.GNUTranslations.gettext`.
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
    python_module_name: str,
    locale_dir: Optional[str] = None,
    enable_fallback: bool = True,
    **kwargs,
) -> tuple[Callable, Callable]:
    """
    Attempt to load localized messages. Supports localized strings which specify plurals.
    Uses the default :mod:`gettext` behaviour to determine the language.

    :param python_module_name:
        Name of the python module to localize. For instance, ``fmepy_module``.
    :param locale_dir: Folder to look for .mo files in.
        If not specified, uses :func:`_get_default_locale_dir`.
    :param enable_fallback:
        Whether to use the original localized strings if a .mo file cannot be found.
    :param kwargs: Keyword arguments to pass to :func:`gettext.translation`.
    :return: Configured :meth:`gettext.GNUTranslations.gettext` and
        :meth:`gettext.GNUTranslations.ngettext`.
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
