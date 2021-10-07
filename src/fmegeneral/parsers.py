from __future__ import absolute_import, division, print_function, unicode_literals

from collections import OrderedDict
from fmeobjects import FMESession
from fmegeneral import fmeutil
from fmegeneral.fmeutil import unicodeToSystem, systemToUnicode
from six import string_types


class OpenParameters(OrderedDict):
    """
    Provides convenient access to the open() parameters given to
    :meth:`pluginbuilder.FMEReader.open` and :meth:`pluginbuilder.FMEWriter.open`.

    Parameter keys that appear multiple times in the parameters list will result in
    values of type :class:`list`.
    This scenario is most likely to be encountered with `+ID` keys,
    though such keys are usually handled
    by :meth:`pluginbuilder.FMEMappingFile.fetchFeatureTypes` instead.

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


class SearchEnvelope(object):
    """An abstraction of the 2D search envelope given by FME that's easier to
    understand.

    Call :meth:`__dict__` to get members as a :class:`dict` for use in
    string substitutions.
    """

    def __init__(self, envelope, coordsys=None):
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
        self.coordSys = coordsys

    def __str__(self):
        return "Envelope<({},{})({},{}) {}>".format(
            self.minX, self.minY, self.maxX, self.maxY, self.coordSys
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
    fme_template_feature_type attribute if present, or
    :meth:`fmeobjects.FMEFeature.getFeatureType` otherwise. These are the feature types
    found on DEF lines when FME writers are in dynamic mode.

    :param FMEFeature feature: Feature to query.
    :return: Feature type to look for on DEF lines.
    :rtype: str
    """
    template_feature_type = feature.getAttribute("fme_template_feature_type")
    return systemToUnicode(template_feature_type or feature.getFeatureType())
