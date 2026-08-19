"""
Miscellaneous utilities.
"""

from __future__ import annotations

from typing import Dict, List, Union

# Nothing here is intended for general use.
__all__ = []


def choice_to_bool(boolean):
    """Convert from string yes/no to boolean.

    :param str boolean: yes|no. Case-insensitive.
    :rtype: bool
    """
    return str(boolean).lower() == "yes"


def string_to_bool(string):
    """
    Converts a string to boolean using FME semantics.
    Intended for parsing boolean values from the FME GUI that were serialized as
    string literals such as yes/no and true/false.

    :param str string: Value to convert.
    :returns: boolean, or None if value wasn't a parseable to boolean
    :rtype: bool
    """
    #  This method is modeled after STF_stringToBoolean from stfutil2.cpp.
    try:
        first_char = string[0].lower()
    except (TypeError, IndexError, AttributeError):
        return None

    if first_char in ("t", "y"):
        return True

    if first_char in ("f", "n"):
        return False

    try:
        return bool(float(string))
    except (TypeError, ValueError):
        return None


def stringarray_to_dict(
    stringarray: List[str], start: int = 0
) -> Dict[str, Union[str, List[str]]]:
    """
    Convert an IFMEStringArray-like list from the FMEObjects Python API into a dict.

    The input list's `start+(2*n)` elements are converted to keys,
    and `start+(2*n)+1` elements are converted to values.
    Duplicate keys cause the corresponding values to be collected into a list.

    :param stringarray: Must have an even number of elements starting from `start`.
    :param start: Start index.
    """
    assert (len(stringarray) - start) % 2 == 0
    result = {}
    for index in range(start, len(stringarray), 2):
        key = stringarray[index]
        value = stringarray[index + 1]
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result
