# coding: utf-8

__version__ = "0.4.3"

import gettext
import os

# The fmetools python module uses the locale folder fmetools/i18n
# Any .mo files should be located there as specified in
# the Python gettext documentation
locale_dir = os.path.join(os.path.dirname(__file__), "i18n")
t = gettext.translation("fmetools", locale_dir, fallback=True)
tr = t.gettext
