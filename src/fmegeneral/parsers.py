from __future__ import absolute_import, division, print_function, unicode_literals

from collections import OrderedDict, namedtuple

import six
from fmeobjects import FMESession, FMEFeature
from pluginbuilder import FMEReader, FMEWriter, FMEMappingFile
from fmegeneral import fmeutil
from six import string_types
import fme


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


def systemToUnicode(original):
    """Try to convert a system-encoded string to a Unicode string. Characters
    that could not be converted are replaced with '?'.

    :type original: str
    :param original: System encoded string to convert.
    :return: The converted string.
    :rtype: six.text_type
    """
    # See PRs #52906-52909.
    if isinstance(original, six.text_type):
        # If input is already a Unicode string, return it as-is.
        return original
    return original.decode(getSystemLocale(), "replace")


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


class OpenParameters(OrderedDict):
    """
    Provides convenient access to the open() parameters given to
    :meth:`FMEReader.open` and :meth:`FMEWriter.open`.

    Parameter keys that appear multiple times in the parameters list will result in
    values of type :class:`list`.
    This scenario is most likely to be encountered with `+ID` keys,
    though such keys are usually handled
    by :meth:`FMEMappingFile.fetchFeatureTypes` instead.

    :ivar str dataset: Dataset value from the first argument to `open()`.
        Should use `decodedDataset` instead.
    :ivar list original: Original parameters passed to `open`.
    """

    def __init__(self, dataset, parameters):
        """
        :type dataset: str or None
        :param dataset: Dataset value from the first argument to the
            reader/writer's `open()`.
        :param list[str] parameters: `open()` parameters.
            Must have an odd number of elements or be empty.
        """
        assert (len(parameters) > 0 and len(parameters) % 2 == 1) or not len(parameters)
        super(OpenParameters, self).__init__()

        self.__session = FMESession()

        # If open() parameters aren't empty, the first element is the dataset.
        self.dataset = dataset

        self.original = parameters

        for i in range(1, len(parameters), 2):
            key, value = systemToUnicode(parameters[i]), systemToUnicode(
                parameters[i + 1]
            )

            if self.__contains__(key):
                # Key already exists in this dictionary.
                # If the existing value is a list, append this value to it.
                # Otherwise, turn existing value into a list and append new value.
                existingValue = self.__getitem__(key)
                if isinstance(existingValue, list):
                    existingValue.append(value)
                else:
                    self.__setitem__(key, [existingValue, value])
            else:
                self.__setitem__(key, value)

    @property
    def decodedDataset(self):
        """
        :returns: The FME-decoded value of the dataset.
        :rtype: str
        """
        return self.__session.decodeFromFMEParsableText(self.dataset)

    def get(self, key, default=None, decode=True):
        """Get an open() parameter.

        :param str key: Key to look for.
        :param str default: Value to return if key not present.
        :param bool decode: Whether to interpret the value as FME encoded,
            and return the decoded value.
        :rtype: str
        """
        value = super(OpenParameters, self).get(key, default)
        if decode and isinstance(value, string_types):
            value = self.__session.decodeFromFMEParsableText(value)
        return value

    def get_flag(self, key, default=False):
        """Get an open() parameter and interpret its value as a boolean.

        :param str key: Key to look for.
        :param bool default: Value to return if key not present.
        :rtype: bool
        """
        value = self.get(key)
        if value is None:
            return default
        if isinstance(value, list):
            return False not in map(fmeutil.stringToBool, value)
        return fmeutil.stringToBool(value)

    def __str__(self):
        return "Open parameters: " + ", ".join(
            "%s: %s" % (key, value) for key, value in self.items()
        )


SearchEnvelope = namedtuple(
    "SearchEnvelope", "min_x min_y max_x max_y coordsys", defaults=(None,)
)


def parse_def_line(def_line, option_names):
    """
    Iterate through elements in a DEF line and extract elements into
    more convenient structures.

    :param list[str] def_line: The DEF line. Must have an even number of elements.
    :param list[str] option_names: If a key matches one of these names,
        it'll be separated from the attributes.
    :return: Tuple of:

        - feature type
        - ordered dictionary of attributes and their types (values may be FME-encoded)
        - dictionary of options and their values

       All keys and values are strings.
    :rtype: str, collections.OrderedDict, dict
    """
    assert len(def_line) % 2 == 0

    session = FMESession()

    attributes, options = OrderedDict(), {}
    for index in range(2, len(def_line), 2):
        key, value = systemToUnicode(def_line[index]), systemToUnicode(
            def_line[index + 1]
        )

        if key in option_names:
            options[key] = session.decodeFromFMEParsableText(value)
        else:
            attributes[key] = value

    return systemToUnicode(def_line[1]), attributes, options


def get_template_feature_type(feature):
    """Get the template feature type of a feature, which is the value of the
    `fme_template_feature_type` attribute if present, or
    :meth:`FMEFeature.getFeatureType` otherwise. These are the feature types
    found on DEF lines when FME writers are in dynamic mode.

    :param FMEFeature feature: Feature to query.
    :return: Feature type to look for on DEF lines.
    :rtype: str
    """
    template_feature_type = feature.getAttribute("fme_template_feature_type")
    return systemToUnicode(template_feature_type or feature.getFeatureType())


class FMEMappingFileWrapper(object):
    """
    A wrapper for accessing information from the mapping file in a simplified way.

    Methods are similar to the 'withPrefix' methods on :class:`FMEMappingFile`.
    However, the plugin keyword and type are assumed to be the ones in the constructor.

    The functionality of this wrapper,
    combined with prefixing of directives in the metafile's `SOURCE_READER` with ``-_``,
    is designed to eliminate the need to look in both open() parameters and the
    mapping file for the same directive.
    Instead, the mapping file can be used exclusively.

    :ivar FMEMappingFile mapping_file: The original mapping file object.
    """

    def __init__(self, mapping_file, plugin_keyword, plugin_type):
        """
        :param FMEMappingFile mapping_file: The original mapping file object.
        :param str plugin_keyword: Plugin keyword string.
        :param str plugin_type: Plugin type string.
        """
        self.mapping_file = mapping_file
        self._plugin_keyword = plugin_keyword
        self._plugin_type = plugin_type

        self.__session = FMESession()

    def def_lines(self):
        """Get an iterable over DEF lines for this plugin.

        :return: iterator
        """
        def_filter = self._plugin_keyword + "_DEF"
        self.mapping_file.startIteration()
        def_line_buffer = self.mapping_file.nextLineWithFilter(def_filter)
        while def_line_buffer is not None:
            yield def_line_buffer
            def_line_buffer = self.mapping_file.nextLineWithFilter(def_filter)

    def fetch_with_prefix(self, plugin_type, plugin_keyword, directive):
        """Like :meth:`FMEMappingFile.fetchWithPrefix`, but also handles the
        Python-specific situation where directive values are returned as
        2-element lists with identical values.

        :param str plugin_type: Plugin type string.
        :param str plugin_keyword: Plugin keyword string.
        :param str directive: Name of the directive.
        :return: If the value is scalar or a 2-element list with identical elements,
            return the element. Otherwise, the list is returned as-is.
        :rtype: str
        """
        value = self.mapping_file.fetchWithPrefix(
            plugin_type, plugin_keyword, directive
        )
        if isinstance(value, list) and len(value) == 2 and value[0] == value[1]:
            return value[0]
        return value

    def get(self, directive, default=None, decode=True, as_list=False):
        """Fetch a directive from the mapping file, assuming the given plugin
        keyword and type.

        :param str directive: Name of the directive.
        :param str default: Value to return if directive not present.
        :param bool decode: Whether to interpret the value as FME-encoded,
            and return the decoded value.
        :param bool as_list:  If true, then parse the value as a space-delimited list,
            and return a list.
        :rtype: str, int, float, list, None
        """
        value = self.fetch_with_prefix(
            self._plugin_keyword, self._plugin_type, directive
        )
        if value is None:
            return default
        if as_list and isinstance(value, six.string_types):
            value = value.split()
            if decode:
                value = [
                    self.__session.decodeFromFMEParsableText(entry) for entry in value
                ]
        elif decode and isinstance(value, six.string_types):
            value = self.__session.decodeFromFMEParsableText(value)
        return value

    def get_flag(self, directive, default=False):
        """Get the specified directive and interpret it as a boolean value.

        :param str directive: Name of the directive.
        :param bool default: Value to return if directive not present.
        :rtype: bool
        """
        value = self.get(directive)
        if value is None:
            return default

        return fmeutil.stringToBool(value)

    def get_search_envelope(self):
        """Get the search envelope, with coordinate system, if any.

        :returns: The search envelope, or None if not set.
        :rtype: parsers.SearchEnvelope, None
        """
        env = self.mapping_file.fetchSearchEnvelope(
            self._plugin_keyword, self._plugin_type
        )
        if not env:
            return None
        coordsys = self.get("_SEARCH_ENVELOPE_COORDINATE_SYSTEM")
        return SearchEnvelope(env[0][0], env[0][1], env[1][0], env[1][1], coordsys)

    def get_feature_types(self, open_parameters, fetch_mode="FETCH_IDS_AND_DEFS"):
        """Get the feature types, if any.

        :param list[str] open_parameters: Parameters for the reader.
        :param str fetch_mode: `FETCH_IDS_AND_DEFS` or `FETCH_DEFS_ONLY`
        :returns: List of feature types.
        :rtype: list[str]
        """
        featTypes = self.mapping_file.fetchFeatureTypes(
            self._plugin_keyword, self._plugin_type, open_parameters, fetch_mode
        )
        if featTypes is None:
            # Mapping file returns None when there are no feature types,
            # but that requires a separate check for None in code that uses it.
            # Eliminate this distinction.
            return []
        return [systemToUnicode(ft) for ft in featTypes]
