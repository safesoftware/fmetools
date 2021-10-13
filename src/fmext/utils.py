"""
Miscellaneous utilities.
"""
from collections import OrderedDict


def choice_to_bool(boolean):
    """Convert from string yes/no to boolean.

    :param str boolean: yes|no. Case-insensitive.
    :rtype: bool
    """
    return str(boolean).lower() == "yes"


def stringarray_to_dict(stringarray, start=0):
    """
    Converts IFMEStringArray-equivalents from the FMEObjects Python API
    into a `dict` that's easier to work with.

    Given a list `stringarray`,
    convert elements `start+(2*n)` to keys, and `start+n` to values.
    Duplicate keys cause the corresponding values to be collected into a list.

    :param list stringarray: Must have an even number of elements starting from `start`
    :param int start: Start index
    :rtype: OrderedDict
    """
    assert (len(stringarray) - start) % 2 == 0
    result = OrderedDict()
    for index in range(start, len(stringarray), 2):
        key, value = stringarray[index], stringarray[index + 1]
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


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
