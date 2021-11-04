__version__ = "0.0.1"

import gettext
import os

# The fmetools python module uses the locale folder fmetools/i81n
# Any .mo files should be located there as specified in
# the Python gettext documentation
locale_dir = os.path.join(os.path.dirname(__file__), "i81n")
t = gettext.translation("fmetools", locale_dir, fallback=True)
tr = t.gettext
