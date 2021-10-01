# coding=utf-8
"""
Utility classes to turn strings, which may be numerical or non-numerical,
into keys that will be default sorted such that numbers come before non-
numerical strings and are sorted according to their numerical value, while
other strings get standard Python string sorting. Items with no specified key
(ie, a None key) will be sorted last by default, although they can be sorted
first. When trying to compare two OrderKeys with different settings for
whether None comes first or last, None will be sorted first.

Constructors can be passed right in to sort(), as in
``list_.sort(key=OrderKey)``, or used in a lambda key function. Can also be
used with sorting methods that do not take a key function (eg, the
functions in bisect) by pre-processing each key into an OrderKey.
"""

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)
import six


class OrderKey(object):
    """Sorting utility class that uses a given key for sorting order."""
    def __init__(self, key, none_first=False):
        """
      :param key: The string to use as a key for sorting.
      :type key: six.string_types, int, or float
      :param none_first: Whether None should be sorted at the beginning
        (if True) or end (if False).
      :type none_first: bool
      """
        self._none_first = none_first
        try:
            self._key = float(key)
        except ValueError:
            self._key = six.text_type(key)
        except TypeError:
            self._key = None

    @property
    def key(self):
        """Once created, an OrderKey should not be changed."""
        return self._key
    
    @property
    def none_first(self):
        """Whether None should be sorted at the beginning (True) or end (False)."""
        return self._none_first

    def __lt__(self, other):
        """Override the default Less Than behaviour.

        Per https://docs.python.org/3/howto/sorting.html, sort routines
        are guaranteed to use __lt__(), so no other overrides are
        necessary
        """
        try:
            if self.key is None:
                return self.none_first or other.none_first
            elif other.key is None:
                return not (self.none_first or other.none_first)
        except AttributeError:
            # Comparison only works when both objects are OrderKeys
            return NotImplemented

        if isinstance(self.key, float):
            if isinstance(other.key, float):
                return self.key < other.key
            else:
                return True
        else:
            if isinstance(other.key, float):
                return False
            else:
                return self.key < other.key


class OrderKeyWithSubkey(OrderKey):
    """Sorting utility class that uses a given key and subkey for sorting order."""
    def __init__(self, key, subkey=None):
        """
      :param key: The string to use as a key for sorting.
      :type key: six.string_types, int, or float
      :param str subkey: The string to use as a secondary key for sorting, in
        case key matches.
      """
        OrderKey.__init__(self, key)

        try:
            self._subkey = float(subkey)
        except ValueError:
            self._subkey = six.text_type(subkey)
        except TypeError:
            self._subkey = None

    @property
    def subkey(self):
        """Read-only."""
        return self._subkey

    def __lt__(self, other):
        """Override the superclass' Less Than behaviour to take subkeys into
        account when the primary keys match."""
        try:
            same_key = self.key == other.key
        except TypeError:
            # If the keys of the two objects cannot be compared using ==,
            # the objects will not be equal
            same_key = False
        except AttributeError:
            return NotImplemented

        if same_key:
            if isinstance(self.subkey, float):
                if isinstance(other.subkey, float):
                    return self.subkey < other.subkey
                else:
                    return True
            else:
                if isinstance(other.subkey, float):
                    return False
                else:
                    return self.subkey < other.subkey
        else:
            return super(OrderKeyWithSubkey, self).__lt__(other)
