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
    """Converts a string to boolean, and returns None if conversion fails.

    :param str string: Value to convert.
    :rtype: bool
    """
    #  This method is modeled after STF_stringToBoolean from stfutil2.cpp.

    if len(string) == 0:
        return None

    first_char = string[0].lower()

    # Check if first character contains "t" or "y".
    if first_char in ["t", "y"]:
        return True

    # Check if first character contains "f" or "n".
    if first_char in ["f", "n"]:
        return False

    # Attempt to convert string to float.
    else:
        try:
            # Returns True if string casts to float as a non-zero number. False if not equal to zero.
            return bool(float(string))
        except (TypeError, ValueError):
            # Conversion failed.
            return None
