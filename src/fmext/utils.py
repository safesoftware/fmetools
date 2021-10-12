"""
Miscellaneous utilities.
"""


def choice_to_bool(boolean):
    """Convert from string yes/no to boolean.

    :param str boolean: yes|no. Case-insensitive.
    :rtype: bool
    """
    return str(boolean).lower() == "yes"


def stringarray_to_dict(stringArray):
    """Given a list, convert odd indicies to keys, and even indicies to values.
    Useful for converting IFMEStringArray-equivalents from the FMEObjects
    Python API into something easier to manipulate.

    :param list stringArray: Must have an even length
    :rtype: dict
    """
    result = {}
    for index in range(0, len(stringArray), 2):
        result[stringArray[index]] = stringArray[index + 1]
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
    except (TypeError, IndexError):
        return None

    if first_char in ["t", "y"]:
        return True

    if first_char in ["f", "n"]:
        return False

    try:
        return bool(float(string))
    except (TypeError, ValueError):
        return None
