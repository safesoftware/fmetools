"""Utilities sharable between internal plugin python modules."""

# --- Import FME and sys requirements
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import re
import sys
import locale
import traceback
from collections import OrderedDict
from datetime import datetime, tzinfo, timedelta

import fme
from fmeobjects import FMEFeature, FMESession

import six
from six import string_types, iteritems, text_type, binary_type, PY2, PY3

import fmeobjects
from fmeobjects import FME_INFORM

from fmegeneral import fmeconstants


class FMELocale(object):
    """Singleton for handling encoding on Mac.

    This class serves no purpose for end users. Use
    :func:`getSystemLocale` instead.
    """

    # See PR#53541 and PR#52908.

    def __init__(self):
        pass

    #: Name of the detected system locale.
    #:
    #: :type: str
    detectedSystemLocale = None


def fmeBoolToBool(boolean):
    """
    Convert an FME boolean to an actual boolean,
    where FME boolean true = 1.

    :type boolean: int or str
    :param boolean: value to convert
    :rtype: bool
    """
    return int(boolean) == 1


def choiceToBool(boolean):
    """Convert from string yes/no to boolean.

    :param str boolean: yes|no. Case-insensitive.
    :rtype: bool
    """
    return str(boolean).lower() == "yes"


def boolToChoice(boolean):
    """Convert from boolean to string Yes/No.

    :param bool boolean: value to convert
    :return: Yes|No
    :rtype: str
    """
    return "Yes" if boolean else "No"


def stringArrayToDict(stringArray):
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


def stringToBool(string):
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


def exceptionToDebugStr():
    """Get the last raised exception trace, type, and message as one line.

    :return: The last raised exception as a one line combined exception trace, type and message.
    :rtype: str
    """
    return repr(traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]))


def exceptionToStr():
    """Get the last raised exception message.

    :return: The last raised exception message.
    :rtype: str
    """
    return str(sys.exc_info()[1])


def getSystemLocale():
    """Get the system locale of the process. The return value is cached after the first time
    this function is called.

    :return: The system locale name.
    :rtype: str
    """
    if FMELocale.detectedSystemLocale is None:
        # FME may change the locale of the process, so query FME to get the system locale truth.
        FMELocale.detectedSystemLocale = fme.systemEncoding

    return FMELocale.detectedSystemLocale


def unicodeToSystem(original):
    """Try to convert the given Unicode string to the system encoding.
    Characters that could not be converted are replaced with '?'. If input is
    already a non-Unicode string, return unchanged. In Python 3, unicode
    strings are returned.

    :type original: `unicode <https://docs.python.org/2.7/library/functions.html#unicode>`_
    :param original: Unicode string to convert.
    :return: The converted string.
    :rtype: six.binary_type or type(original)
    """
    # See PRs #52906-52909.

    if (PY2 and isinstance(original, binary_type)) or (PY3 and isinstance(original, text_type)):
        # If input is already a non-Unicode string, return it as-is.
        # In Py3, Unicode strings are returned.
        return original
    return original.encode(getSystemLocale(), "replace")


def castToUnicode(string):
    """Method that will catch any edge cases, like floats in attribute
    contents, when encoding in unicode.

    :param str string: Content that is being encoded.
    :return: Unicode content.
    :rtype: six.text_type
    """

    if isinstance(string, string_types):
        return systemToUnicode(string)
    else:
        return text_type(string)


def systemToUnicode(original):
    """Try to convert a system-encoded string to a Unicode string. Characters
    that could not be converted are replaced with '?'.

    :type original: str
    :param original: System encoded string to convert.
    :return: The converted string.
    :rtype: six.text_type
    """
    # See PRs #52906-52909.
    if isinstance(original, text_type):
        # If input is already a Unicode string, return it as-is.
        return original
    return original.decode(getSystemLocale(), "replace")


# -----------------------------------------------------------------------------
# Attempts to convert the given system value to utf-8 encoding
# All characters that failed to encode will be replaced by ?
# Initially added for PRs #53185
# -----------------------------------------------------------------------------
def systemToUtf8(original):
    """Try to convert the given system-encoded string to a UTF-8 encoded
    string. Characters that could not be converted are replaced with '?'.

    :type original: six.binary_type
    :param original: System encoded string to convert.
    :return: UTF-8 encoded string - not a `unicode` string.
    :rtype: six.binary_type
    """
    unicodeVal = original.decode(getSystemLocale(), "replace")
    return unicodeVal.encode("utf8", "replace")


def utf8ToSystem(original):
    """Try to convert the given UTF-8 string to system encoding. Characters
    that could not be converted are replaced with '?'.

    :param six.binary_type original: UTF-8 encoded string.
    :return: System encoded string.
    :rtype: six.binary_type
    """
    # See PR#53185.

    unicodeVal = original.decode("utf8", "replace")
    return unicodeVal.encode(getSystemLocale(), "replace")


def decodeWWJDString(encoded):
    """Decode the input WWJD encoded string to a six.text_type. If encoded
    is not a six.string_types it is returned unchanged.

    :param six.string_types encoded: WWJD encoded string.
    :return: Decoded WWJD string or input value unchanged.
    :rtype: six.text_type or type(encoded)
    """
    return (
        FMESession().decodeFromFMEParsableText(encoded)
        if isinstance(encoded, six.string_types)
        else encoded
    )


class Logger(object):
    """Helper class for logging functionality.

    A wrapper around :class:`fmeobjects.FMELogFile`.
    """

    def __init__(self, debug=False):
        """
        :param bool debug: Whether this instance should emit debug messages.
        """
        self.debug_ = debug
        self.fmeLogfile_ = fmeobjects.FMELogFile()

    def setDebugMode(self, debug=True):
        """Tells the logger whether to emit debug messages or not.

        :param bool debug: Whether this instance should emit debug messages.
        """
        self.debug_ = debug

    def logMessageString(self, message, level=FME_INFORM, debug=False):
        """Write message string to the FME logfile.

        :param str message: Message to write to the log.
        :param int level: Message severity level.
        :param bool debug: If True, then this message will only be logged if this
           :class:`Logger` instance is in debug mode.
        """
        # Output non-debug messages
        if not debug:
            self.fmeLogfile_.logMessageString(message, level)

        # Output debug messages
        elif self.debug_:
            self.fmeLogfile_.logMessageString("DEBUG: %s" % message, level)

    def logMessage(self, messageID, params=None, level=FME_INFORM, debug=False):
        """Write message based on its message ID or string to the FME logfile.

        :type messageID: str or int
        :param messageID: Message ID or message string to write to the log.
        :param list params: List of string substitution arguments for the given message.
        :param int level: Message severity level.
        :param bool debug: If True, then this message will only be logged if this
           :class:`Logger` instance is in debug mode.
        """
        if params is None:
            params = []
        for index, value in enumerate(params):
            # All message parameters must be strings, or else the logger will not perform the substitution.
            if not isinstance(value, string_types):
                params[index] = str(value)

        # Output non-debug messages
        if not debug:
            if params is None:
                self.fmeLogfile_.logMessageString(messageID, level)
            else:
                self.fmeLogfile_.logMessage(messageID, params, level)

        # Output debug messages
        elif self.debug_:
            if params is None:
                self.fmeLogfile_.logMessageString(messageID, level)
            else:
                self.fmeLogfile_.logMessage(messageID, params, level)

    def logFeature(self, feature, level=FME_INFORM, debug=False):
        """Write a feature to the log.

        :param fmeobjects.FMEFeature feature: Feature to log.
        :param int level: Message severity level.
        :param bool debug: If True, then this feature will only be logged if this
           :class:`Logger` instance is in debug mode.
        """
        # Output non-debug messages
        if not debug:
            self.fmeLogfile_.logFeature(feature, level)

        # Output debug messages
        elif self.debug_:
            self.fmeLogfile_.logFeature(feature, level)

    def logProxy(self, log_prefix, proxy_url):
        """Log the given proxy server URL using the appropriate message, but
        with any credentials present in the URL stripped out.

        :param str log_prefix: String to prefix the log message.
           Usually the format name and direction of the invoking format.
        :param str proxy_url: Proxy URL, which may contain the username and password.
        :rtype: None
        """
        credentials_separator_index = proxy_url.rfind("@")
        if credentials_separator_index > -1:
            # Strip out credentials if they're present.
            proxy_url = (
                proxy_url[: proxy_url.find("://") + 3]
                + proxy_url[credentials_separator_index + 1 :]
            )
        self.logMessage(fmeconstants.kFME_MSGNUM_USING_PROXY, [log_prefix, proxy_url])

    def allowDuplicateMessages(self, allowDuplicateMessages):
        """If True, tells the logger not to hide repeated messages.  If False
        the logger will hide repeated lines.

        :param bool allowDuplicateMessages: If True display repeated lines in log
        """
        self.fmeLogfile_.allowDuplicateMessages(allowDuplicateMessages)

    def getAllowDuplicateMessages(self):
        """Returns the status of the handling of duplicated messages in the
        logger. If True the logger is set to display repeated lines.  If False
        the logger will hide repeated lines.

        :rtype: bool
        """
        return self.fmeLogfile_.getAllowDuplicateMessages()

    def getMessage(self, messageNumber, messageParameters):
        """Returns a formatted message using the given params.

        :type messageParameters: list[six.text_type]
        :param int messageNumber: The message number to look up.
        :param messageParameters: The list of arguments.
        :rtype: six.text_type
        """
        return self.fmeLogfile_.getMessage(messageNumber, messageParameters)


class FMETZInfo(tzinfo):
    """Rudimentary class that represents an arbitrary time zone offset.

    Used in :func:`fmeDateToPython`, but probably not useful for end
    users.
    """

    def __init__(self, offset):
        """
        :param int offset: Time zone offset, in minutes
        """
        super(FMETZInfo, self).__init__()
        self.offset = offset

    def utcoffset(self, dt):
        return timedelta(minutes=self.offset)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return None


def fmeDateToPython(dateStr):
    """Convert an FME datetime/date/time to a Python datetime/date/time object.

    If time or datetime successfully parsed, the result will always have microseconds,
    as Python doesn't have a concept of null microseconds.

    :type dateStr: six.text_type
    :param dateStr: An FME datetime string
    :returns: Python datetime object, has date, has time
    :rtype: datetime.datetime
    """

    def microsecond_format(value):
        """
        :param value: Microseconds or nanoseconds. Can be `None`.
           Though FME datetime format supports nanoseconds, Python datetime does not, so it's truncated.
        :rtype: str
        :returns: 6-character value suitable for parsing as `%f` in :meth:`datetime.strptime`.
        """
        if value is None:
            value = ""
        # Python 2 rejects unicode fill character, and we have unicode_literals on.
        return value.ljust(6, b"0" if six.PY2 else "0")[:6]

    # Ensure it's a string.
    if not isinstance(dateStr, string_types):
        dateStr = str(dateStr)

    regex = r"(?P<dt>\d+)(?:\.(?P<us>\d+))?(?:(?P<tzs>[\-+])(?P<tzh>[01][0-9])(?::(?P<tzm>[0-5][0-9]))?)?"
    match = re.match(regex, dateStr)
    if match is None:
        # If regex doesn't match, then it's unparseable.
        return None, False, False

    dt, us, tzs, tzh, tzm = match.group("dt", "us", "tzs", "tzh", "tzm")

    tz = None
    if tzs is not None:
        # If timezone sign is present, convert time zone offset to minutes,
        # and make a tzinfo object to represent it.
        tz = int(tzh) * 60
        if tzm:
            tz += int(tzm)
        if tzs == "-":
            tz *= -1
        tz = FMETZInfo(tz)

    fmeDateFormat, fmeTimeFormat = "%Y%m%d", "%H%M%S%f"

    dtSize = len(dt)
    try:
        if dtSize == 8:
            # Parse date.
            return datetime.strptime(dt, fmeDateFormat), True, False
        if dtSize == 6:
            # Parse time plus microseconds, and time zone if present.
            dt += microsecond_format(us)
            theTime = datetime.strptime(dt, fmeTimeFormat)
            theTime = theTime.replace(tzinfo=tz)
            return theTime, False, True
        if dtSize == 14:
            # Parse datetime plus microseconds, and time zone if present.
            dt += microsecond_format(us)
            fmt = fmeDateFormat + fmeTimeFormat
            theDateTime = datetime.strptime(dt, fmt)
            theDateTime = theDateTime.replace(tzinfo=tz)
            return theDateTime, True, True
    except ValueError:
        # Any kind of parsing error, including impossible dates/times,
        # shall return None.
        return None, False, False

    # Failed to parse.
    return None, False, False


def pythonDateTimeToFMEFormat(theDateTime):
    """Convert a Python datetime to a string in FME date format. Works around
    issue of strftime() refusing to output anything for datetimes before 1900.

    :param datetime.datetime theDateTime: A valid Python datetime
    :return: The converted value.
    :rtype: six.text_type
    """

    # Get the time tuple and concatenate the first 6 values (date and time).
    # Time tuple doesn't contain time zone or microseconds, so those parts are added separately.
    timetuple = theDateTime.timetuple()
    result = str(timetuple.tm_year).zfill(4)
    result += "".join(str(timetuple[i]).zfill(2) for i in range(1, 6))

    # Add microseconds if they're not zero.
    microseconds = theDateTime.microsecond
    if microseconds > 0:
        result += "." + str(microseconds).zfill(6)

    # Add time zone offset if the datetime has a time zone.
    tz = theDateTime.tzinfo
    if tz:
        # Get time zone offset in minutes.  The // operator is discard floor division.
        totalOffsetMinutes = int(tz.utcoffset(False).total_seconds()) // 60
        offsetH, offsetM = abs(totalOffsetMinutes) // 60, abs(totalOffsetMinutes) % 60
        result += "+" if totalOffsetMinutes >= 0 else "-"  # Sign.
        result += str(offsetH).zfill(2)  # Hours.
        if offsetM > 0:  # Include minutes if they're not zero.
            result += str(offsetM).zfill(2)

    return result


UTC_TZ = FMETZInfo(0)


def unixtimeToPython(timestamp_ms):
    """Parse millisecond unix timestamps to Python datetime in UTC. Supports
    negative timestamps. Use this function instead of
    :meth:`datetime.date.fromtimestamp`.

    :param int timestamp_ms: Unix timestamp in milliseconds. Negative values are okay.
    :returns: Python datetime, with UTC timezone.
    :rtype: datetime.datetime
    """
    timestamp_s, timestamp_ms_part = timestamp_ms // 1000, timestamp_ms % 1000
    if timestamp_ms < 0:
        return datetime(1970, 1, 1, tzinfo=UTC_TZ) + timedelta(
            seconds=timestamp_s, milliseconds=timestamp_ms_part
        )
    return datetime.fromtimestamp(timestamp_s, tz=UTC_TZ).replace(
        microsecond=timestamp_ms_part * 1000
    )


def isoTimestampToFMEFormat(isoTimestamp):
    """Convert an ISO timestamp to FME format. Doesn't try to actually parse
    and validate the timestamp. Since the standard library doesn't include a
    way to parse ISO 8601 timestamps, this function is a simple but imperfect
    way/ to avoid using another third-party library.

    Examples:

    =============================  =======================
    ISO 8601                       FME format
    =============================  =======================
    2014-04-15T16:54:20Z           20140415165420+00
    2014-04-15T16:54:20.123+05:30  20140415165420.123+0530
    =============================  =======================

    :type isoTimestamp: six.text_type
    :param isoTimestamp: ISO 8601-formatted timestamp.
    :return: Timestamp in FME format, or None if timestamp could not be parsed
    :rtype: six.text_type or None
    """
    if not isinstance(isoTimestamp, text_type):
        try:
            isoTimestamp = systemToUnicode(isoTimestamp)
        except UnicodeEncodeError:
            return None

    # Remove date/time separator, time part, and timezone part separator.
    formatted = isoTimestamp.replace("T", "")
    formatted = formatted.replace(" ", "")
    formatted = formatted.replace(":", "")
    formatted = formatted.replace("-", "", 2)  # Remove first 2 dashes: the date part separator.

    # Minimum timestamp length is 14 characters/digits to represent both date and time.
    if len(formatted) < 14:
        return None

    # Replace Z timezone with explicit offset.
    if formatted[-1] == "Z":
        formatted = formatted.replace("Z", "+00")

    return formatted


def parse_gui_date(value, raise_on_error=True):
    """Parse a string representation of a date into an object. The string
    representation can be:

    * ``YYYYMMDD`` - as set by ``GUI DATE`` and ``GUI DYNAMIC_MULTI_SELECT`` with ``FME_RESULT_TYPE,DATE``
    * ``YYYY-MM-DD`` - as shown in the UI, and what users are expected to type manually
      when the GUI types above become plaintext fields in the Navigator.

    :param str value: Date string to parse, in either ``YYYYMMDD`` or ``YYYY-MM-DD`` form.
    :param bool raise_on_error: If False, return None instead of raising errors.
    :rtype: datetime.datetime
    :raises ValueError: If value couldn't be parsed, and `raise_on_error` is True.
    """
    # For details about this discrepancy, see PR77997.

    value = value.replace("-", "")
    try:
        return datetime.strptime(value, "%Y%m%d")
    except:
        if not raise_on_error:
            return
        raise


def retryOnException(
    exception,
    maxTries,
    logWrapper=lambda attempt, maximum: None,
    action=lambda *x: None,
    *actionArgs,
    **actionKwargs
):
    """Function generating a decorator to retry a function several times,
    taking an action on a specific exception. When maximum retries have been
    made, the exception is raised again.

    :param class exception: The exception class
    :param int maxTries: The maximum number of times to try. On a failed attempt 'maxTries', the exception is re-raised
    :param function logWrapper: A logging function which will be called with logWrapper(attempt, maxRetries) on each retry
    :param function action: A function to call in case of exception, before retrying
    :param actionArgs: Arguments to pass to the action function
    :param actionKwargs: Keyword arguments to pass to the action function
    :return: The decorator
    """

    def actualDecorator(function):
        """The actual decorator which uses the arguments from
        retryOnException."""

        def decorated_func(*args, **kwargs):
            """The decorated function which will be returned by
            actualDecorator."""
            for i in range(0, maxTries):
                if i > 0:
                    logWrapper(i, maxTries - 1)
                try:
                    return function(*args, **kwargs)
                except exception as e:
                    if i < maxTries - 1:
                        action(*actionArgs, **actionKwargs)
                    else:
                        raise e

        return decorated_func

    return actualDecorator


def mangleDuplicateName(candidateName, usedNames):
    """Generate unique names for otherwise duplicated feature type or attribute
    names, in the same way FME Workbench would.

    :param str candidateName: The input name,
       just as if the user typed it into the corresponding field on the User Attributes tab.
       The input value needs to be encoding-mangled, if applicable.
    :param set[str] usedNames: Set of already-assigned names.
       The caller is responsible for adding the name returned by this function to this set.
    :return: Mangled name, guaranteed unique among `usedNames`.
    :rtype: str
    """
    if candidateName not in usedNames:
        # Name not duplicated.
        return candidateName

    mangleIndex = 0
    while True:
        mangledName = "%s%02d" % (candidateName, mangleIndex)
        if mangledName not in usedNames:
            return mangledName
        mangleIndex += 1


def parseMultiParam(multiparam, delim=";", decode=False):
    """Creates a dictionary from an FME MULTIPARAM

    Example:

       ``SMTP_GROUP;;HOST;email3;PORT;25;ENCRYPTION;None;TIMEOUT;5;``
       ``AUTHENTICATION;NO;USERNAME;<Unused>;PASSWORD;<Unused>``

    :param str multiparam: The multiparam string to be parsed
    :param str delim: The delimiter (optional), defaults to ``;``
    :return: A dictionary with key-value PARAM=value

       Example: ``{ HOST: "email3", PORT: "25", ... }``
    :rtype: dict
    """

    def generatePairs(iterable):
        iterator = iter(iterable)
        try:
            while True:
                key, value = next(iterator), next(iterator)
                # PR70661: Generically apply @Concatenate() to decrypt fme_decrypt() values.
                if value.startswith("fme_decrypt("):
                    value = FMEFeature().performFunction("@Concatenate({})".format(value))
                if value != "":
                    yield key, value
                else:
                    continue
        except StopIteration:
            pass

    # multiparam = multiparam.split(delim * 2)[-1]
    multiparam = multiparam.split(delim)

    return dict(generatePairs(multiparam))


def replaceMultiparam(multi, param, value, delim=";"):
    """Sets the multiparameter with a new value for attribute.

    :param str multi: The multiparam string
    :param str param: The name of the parameter
    :param str value: The new value of the parameter
    :param str delim: The delimiter, default ``;``
    :returns: New value for multiparam.
    :rtype: str
    """
    # Adapted from slocke's fmegeocoder unit tests.

    attr = param + delim
    findIndex = multi.find(attr)
    if findIndex < 0:
        findIndex = len(multi)
        attr = delim + attr
    prefix = multi[0:findIndex]
    remove = multi[findIndex : len(multi)]
    findIndex = remove.find(delim, len(attr))
    if findIndex < 0:
        findIndex = len(remove)
    suffix = remove[findIndex : len(remove)]
    return prefix + attr + str(value) + suffix


def zipProperties(category, properties):
    """Return a list where each odd index is category, and each even index is a
    property.

    Example:

       ``[category, property[0], category, property[1], ..., category, property[n]]``

    :param str category: Property category.
    :param list[str]|None properties: Property values for the category. Can be empty or None.
    :returns: None if properties list is empty. Otherwise, the returned list has an even number of string elements.
    :rtype: list[str]
    """
    if not properties:
        return None
    categories = [category] * len(properties)
    completed = categories + properties
    completed[::2] = categories  # Odd indexes.
    completed[1::2] = properties  # Even indexes.
    return completed


def build_feature(feature_type, attrs=None, attr_types=None, geometry=None, coord_sys=None):
    """Build an :class:`fmeobjects.FMEFeature` instance with the most frequently used
    parameters.

    This helper function reduces verbosity and boilerplate code associated with FMEFeature construction.
    It also helps avoid common pitfalls such as:

    * Undefined geometry on feature
    * Calling :meth:`fmeobjects.FMEFeature.setAttribute` with a `None` value

    To build schema features, use :func:`build_schema_feature` instead.

    :param str feature_type: The feature type.
    :param dict attrs: Attribute names and values.
    :param dict attr_types: Attribute names and their fmeobjects type.
       This is used for setting null attribute values.
       If not specified, or if there's no mapping for a given attribute name,
       then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    :param fmeobjects.FMEGeometry geometry: Geometry to put on the feature.
    :param str coord_sys: Coordinate system name to set.
    :rtype: fmeobjects.FMEFeature
    """
    feature = FMEFeature()
    feature.setFeatureType(feature_type)
    feature.setGeometry(geometry)
    if coord_sys:
        feature.setCoordSys(coord_sys)

    if attrs:
        for attr_name, value in iteritems(attrs):
            if value is None:
                if attr_types is None:
                    attr_types = {}
                # FME_ATTR_UNDEFINED is silently interpreted as FME_ATTR_STRING.
                feature.setAttributeNullWithType(
                    attr_name, attr_types.get(attr_name, fmeobjects.FME_ATTR_STRING)
                )
            else:
                feature.setAttribute(attr_name, value)

    return feature


def build_schema_feature(feature_type, schema_attrs=None, fme_geometries=None):
    """Build an :class:`fmeobjects.FMEFeature` suitable for returning from
    :meth:`pluginbuilder.FMEReader.readSchema`. Helps avoid common pitfalls such as:

    * Setting any geometry on the feature
    * Setting non-user attributes as sequenced attributes
    * Setting user attributes as regular attributes

    :param str feature_type: The feature type.
    :param collections.OrderedDict schema_attrs: Ordered schema attributes for the feature type.
       Keys are attribute names, and values are format-specific attribute types.
    :param list fme_geometries: Format-specific geometry types for this feature type.
    :rtype: fmeobjects.FMEFeature
    """
    assert isinstance(schema_attrs, OrderedDict) or not schema_attrs
    if schema_attrs is None:
        schema_attrs = {}

    feature = FMEFeature()
    feature.setFeatureType(feature_type)
    if fme_geometries:
        feature.setAttribute(fmeobjects.kFMERead_Geometry, fme_geometries)

    for attr_name, value in iteritems(schema_attrs):
        assert value
        feature.setSequencedAttribute(attr_name, value)

    return feature


def set_list_attribute_with_properties(feature, index, property_attrs, attr_types=None):
    """Set a list attribute entry onto a feature, where the entry is comprised
    of one or more properties, e.g.: ``name{i}.property``.

    To set a property-less list attribute comprised of strings,
    use :meth:`fmeobjects.FMEFeature.setAttribute` instead.

    :param fmeobjects.FMEFeature feature: Feature to receive the list attribute.
    :param int index: Index into the list attribute to set.
    :param dict property_attrs: List attribute names and values.
       All attribute names must follow the format ``name{}.property``.
       The empty braces will get filled with the index.
    :param dict attr_types: Attribute names and their fmeobjects type.
       This is used for setting null attribute values.
       If not specified, or if there's no mapping for a given attribute name,
       then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    """
    for attr_name, value in iteritems(property_attrs):
        assert "{}" in attr_name
        final_attr_name = attr_name.replace("{}", "{%s}" % index, 1)
        if value is None:
            if attr_types is None:
                attr_types = {}
            # FME_ATTR_UNDEFINED is silently interpreted as FME_ATTR_STRING.
            feature.setAttributeNullWithType(
                final_attr_name, attr_types.get(attr_name, fmeobjects.FME_ATTR_STRING)
            )
        else:
            feature.setAttribute(final_attr_name, value)


def aggressive_normpath(path):
    """
    Path normalization that accepts Windows or Unix paths and normalizes them to the current
    platform.

    This means you can use backslashes on Linux, which is something FME might give us on a cross-
    platform workspace.

    :type path: six.text_type
    :param path: The input path
    :return: The normalized path.
    :rtype: six.text_type
    """
    standard_seps_path = os.path.sep.join(re.split(r"[\\/]", path))
    return os.path.normpath(standard_seps_path)


def remove_invalid_path_chars(path, allow_separators=True):
    """
    Replaces all potentially questionable characters from a path with underscores (_).

    :param str path: the raw path
    :param bool allow_separators: whether to allow slashes in the path (i.e. is this just a filename
        or is it a full path?)
    :return: the sanitized path
    :rtype: str
    """

    pattern = r"[\r\n\t\0"

    # Windows is stricter than posix
    if os.name == "nt":
        pattern += r'<>:"|?*'

    if not allow_separators:
        pattern += r"\\\/"
    pattern += r"]"

    return re.sub(pattern, "_", path)
