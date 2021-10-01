from __future__ import absolute_import, division, print_function, unicode_literals

from collections import OrderedDict
from fmeobjects import FMESession
from fmegeneral import fmeutil
from fmegeneral.fmeconstants import kFME_TEMPLATE_FEATURE_TYPE
from fmegeneral.fmeutil import unicodeToSystem, systemToUnicode
from six import string_types


class OpenParameters(OrderedDict):
    """Interpret the open() parameters given to :meth:`pluginbuilder.FMEReader.open` and
    :meth:`pluginbuilder.FMEWriter.open`.

    Parameter keys that appear multiple times in the parameters list will result in values of type :class:`list`.
    This scenario is most likely to be encountered with `+ID` keys, though such keys are usually handled
    by :meth:`pluginbuilder.FMEMappingFile.fetchFeatureTypes` and not within this class.

    :param str dataset: Dataset value from the first argument to `open()`. Should use `decodedDataset` instead.
    :param list original: Original parameters passed to `open`.
    """

    def __init__(self, dataset, parameters):
        """
        :type dataset: str or None
        :param dataset: Dataset value from the first argument to `open()`. Should use `decodedDataset` instead.
        :param list[str] parameters: open() parameters. Must have an odd number of elements or be empty.
        """
        assert (len(parameters) > 0 and len(parameters) % 2 == 1) or len(parameters) == 0
        super(OpenParameters, self).__init__()

        self.__session = FMESession()

        # If open() parameters aren't empty, the first element is the dataset.
        self.dataset = dataset

        self.original = parameters

        for i in range(1, len(parameters), 2):
            key, value = systemToUnicode(parameters[i]), systemToUnicode(parameters[i + 1])

            if self.__contains__(key):
                # Key already exists in this dictionary.
                # If the existing value is a list, append this value to it.
                # Otherwise, turn existing value into a list with existing and new values.
                existingValue = self.__getitem__(key)
                if isinstance(existingValue, list):
                    existingValue.append(value)
                else:
                    self.__setitem__(key, [existingValue, value])
            else:
                self.__setitem__(key, value)

    @property
    def decodedDataset(self):
        """Get the WWJD-decoded value of the dataset.

        :rtype: six.text_type
        """
        return self.__session.decodeFromFMEParsableText(self.dataset)

    def get(self, key, default=None, decodeWWJD=True):
        """Get an open() parameter.

        :type key: six.text_type
        :param key: Key to look for.
        :param str default: Value to return if key not present.
        :param bool decodeWWJD: Whether to interpret the value as WWJD-encoded, and return the decoded value.
        :rtype: six.text_type
        """
        value = super(OpenParameters, self).get(key, default)
        if decodeWWJD and isinstance(value, string_types):
            value = self.__session.decodeFromFMEParsableText(value)
        return value

    def getFlag(self, key, default=False):
        """Get an open() parameter and interpret its value as a boolean.

        :type key: six.text_type
        :param key: Key to look for.
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


class SearchEnvelope(object):
    """An abstraction of the 2D search envelope given by FME that's easier to
    understand.

    Call :meth:`__dict__` to get members as a :class:`dict` for use in
    string substitutions.
    """

    def __init__(self, envelope, coordSys=None):
        """
        :param list[list[float]] envelope: [[minX, minY], [maxX, maxY]]
        """
        self.envelope = envelope
        self.bottomLeft = envelope[0]
        self.topRight = envelope[1]
        self.minX = envelope[0][0]
        self.minY = envelope[0][1]
        self.maxX = envelope[1][0]
        self.maxY = envelope[1][1]
        self.coordSys = coordSys

    def __str__(self):
        return "Envelope<({},{})({},{}) {}>".format(
            self.minX, self.minY, self.maxX, self.maxY, self.coordSys
        )


def parse_def_line(def_line, option_names):
    """Iterate through elements in a DEF line and extract elements into easier-
    to-use structures.

    :param list[str] def_line: The DEF line. Must have an even number of elements.
    :param list[str] option_names: If a key matches one of these names, it'll be separated from the attributes.
    :return: Tuple of Unicode feature type, ordered dictionary of attributes and their types,
       and dictionary of options and their values. Values in the options dictionary are WWJD-decoded.
       All keys and values are in Unicode.
    :rtype: str, collections.OrderedDict, dict
    """
    assert len(def_line) % 2 == 0

    session = FMESession()

    attributes, options = OrderedDict(), {}
    for index in range(2, len(def_line), 2):
        key, value = systemToUnicode(def_line[index]), systemToUnicode(def_line[index + 1])

        if key in option_names:
            options[key] = session.decodeFromFMEParsableText(value)
        else:
            attributes[key] = value

    return systemToUnicode(def_line[1]), attributes, options


def get_template_feature_type(feature):
    """Get the template feature type of a feature, which is the value of the
    fme_template_feature_type attribute if present, or
    :meth:`fmeobjects.FMEFeature.getFeatureType` otherwise. These are the feature types
    found on DEF lines when FME writers are in dynamic mode.

    :param fmeobjects.FMEFeature feature: Feature to query.
    :return: Feature type to look for on DEF lines. Converted to Unicode.
    :rtype: six.text_type
    """
    template_feature_type = feature.getAttribute(kFME_TEMPLATE_FEATURE_TYPE)
    return systemToUnicode(template_feature_type or feature.getFeatureType())


class JSONOptionParser(object):
    """Parse writer DEF line options common to formats that use
    ``install/metafile/jsonWriterConfig.fmi``."""

    OPTION_PREFIX = "fme_json_document_"
    SOURCE_OPTION_ATTR = OPTION_PREFIX + "source"
    SOURCE_PARAMS_OPTION_ATTR = OPTION_PREFIX + "source_params"
    OPTION_ATTRS = {SOURCE_OPTION_ATTR, SOURCE_PARAMS_OPTION_ATTR}
    """DEF line option names handled by this parser. Include these in the writer's set of recognized DEF line options."""

    DOCUMENT_SOURCE_FEATURE = "Feature"
    DOCUMENT_SOURCE_ATTRIBUTE = "JSON Attribute"

    INNER_PARAM_DOCUMENT_ID_ATTR = OPTION_PREFIX + "id_attribute"
    INNER_PARAM_DOCUMENT_JSON_ATTR = OPTION_PREFIX + "json_attribute"

    def __init__(self, def_line_options):
        """
        :param dict def_line_options: This class will not modify this parameter.
        """
        self.def_options = def_line_options
        self.inner_params = {}

        source_params = def_line_options.get(self.SOURCE_PARAMS_OPTION_ATTR, "").split(";")
        if len(source_params) >= 2:
            session = FMESession()
            for i in range(0, len(source_params), 2):
                self.inner_params[source_params[i]] = session.decodeFromFMEParsableText(
                    source_params[i + 1]
                )

    def document_source(self):
        """Gets the document source setting value.

        :return: Document source setting value, or 'Feature' if not set.
        """
        return self.def_options.get(self.SOURCE_OPTION_ATTR, self.DOCUMENT_SOURCE_FEATURE)

    def document_source_is_feature(self):
        """Returns True if the writer should build JSON documents out of the Feature.

        :returns: True if the writer should build JSON documents out of the Feature.
           Otherwise, the writer should get JSON documents out of the attribute specified by :meth:`json_attribute`.
        :rtype: bool
        """
        return self.document_source() == self.DOCUMENT_SOURCE_FEATURE

    def json_attribute(self):
        """Gets the name of the attribute containing document JSON.

        :return: Name of attribute that contains document JSON. Forced from Unicode to system if necessary.
        :raises KeyError: if not configured. Empty string counts as 'configured'.
        """
        return unicodeToSystem(self.inner_params[self.INNER_PARAM_DOCUMENT_JSON_ATTR])

    def id_attribute(self):
        """Gets the name of the attribute containing document IDs.

        :return: Name of attribute that contains document IDs. Forced from Unicode to system if necessary.
        :raises KeyError: If not configured. Empty string counts as 'configured'.
        """
        return unicodeToSystem(self.inner_params[self.INNER_PARAM_DOCUMENT_ID_ATTR])
