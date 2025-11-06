# coding: utf-8
"""
This module contains parsers to support FME reader/writer development.
It is not intended for general use.
"""

from __future__ import annotations

import dataclasses
import re
from collections import OrderedDict, namedtuple
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterable, Union, Set, Dict, Optional, List, Generator

import fme
import six
from fmeobjects import FMEFeature, FMESession, kFME_ReaderPropAll, kFMERead_SearchType  # noqa F401
from pluginbuilder import FMEMappingFile  # noqa F401
from six import string_types

from . import tr
from .guiparams import parse_gui_type
from .utils import string_to_bool

# Nothing here is intended for general use.
__all__ = []


def _system_to_unicode(original):
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
    return original.decode(fme.systemEncoding, "replace")


def _parse_raw_attr_type(raw_attr_type: str) -> "UserAttributeInfo":
    """
    Parse a DEF line attribute type into an attribute type and optional width, precision, and index fields.
    """
    attr_pattern = r"(?P<attr_type>\w+)(\((?P<width>\d+)(,(?P<precision>\d+))?\))?(,(?P<attr_index>\w+))?"
    match = re.match(attr_pattern, raw_attr_type)
    if match is None:
        # couldn't parse (this shouldn't happen), return the entire type as the base attribute type
        return UserAttributeInfo(raw_attr_type)

    width = match.group("width")
    if width is not None:
        width = int(width)
    precision = match.group("precision")
    if precision is not None:
        precision = int(precision)

    return UserAttributeInfo(
        match.group("attr_type"), width, precision, match.group("attr_index")
    )


def stringarray_to_dict(stringarray, start=0):
    """
    Converts IFMEStringArray-like lists from the FMEObjects Python API
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
        key = _system_to_unicode(stringarray[index])
        value = _system_to_unicode(stringarray[index + 1])
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def parse_def_line(def_line, option_names):
    """
    Iterate through elements in a DEF line and extract elements into
    more convenient structures.

    :param list[str] def_line: The DEF line. Must have an even number of elements.
    :param set option_names: If a key matches one of these names,
        it'll be separated from the attributes.
    :return: Tuple of:

        - Feature type
        - OrderedDict of attributes and their types
        - dict of options and their values, FME-decoded.
          All `option_names` are guaranteed to be keys in this dict,
          with a value of `None` if the option wasn't present on the DEF line.
    :rtype: DefLine
    """
    assert len(def_line) % 2 == 0

    def decode(v):
        if isinstance(v, list):
            return [decode(x) for x in v]
        return v if v is None else FMESession().decodeFromFMEParsableText(v)

    attributes = stringarray_to_dict(def_line, start=2)
    options = {option: decode(attributes.pop(option, None)) for option in option_names}
    return DefLine(_system_to_unicode(def_line[1]), attributes, options)


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
    return _system_to_unicode(template_feature_type or feature.getFeatureType())


def get_feature_operation(
    feature: FMEFeature,
    feature_type_info: "FeatureTypeInfo",
    log,
    supported_fme_db_operations: Iterable[str] = ("INSERT",),
) -> Optional[str]:
    """
    Get the feature operation which the writer should use for the input feature.

    If the configuration is somehow invalid, logs a warning and returns ``None``.
    Callers are expected to skip the feature if a `None` return value is received.

    :param feature: input feature to the writer
    :param feature_type_info: feature type information for the current feature
    :param log: the writer logger
    :param supported_fme_db_operations: supported feature operations when the writer is in fme_db_operation mode
    """
    fme_db_operation_value = feature.getAttribute("fme_db_operation")
    operation_type = feature_type_info.parameters["fme_feature_operation"]

    if operation_type == "MULTIPLE":
        # when using fme_db_operation, we need to check that our value is supported
        # if the fme_db_operation value is missing, the feature operation defaults to insert
        fme_db_operation_value = fme_db_operation_value or "INSERT"
        operation_type = fme_db_operation_value.upper()
        if operation_type not in supported_fme_db_operations:
            log.warning(
                tr("The fme_db_operation value '%s' is not supported")
                % fme_db_operation_value
            )
            return None
        return operation_type

    if fme_db_operation_value and fme_db_operation_value.upper() != operation_type:
        # an fme_db_operation value exists on the feature, but it does not agree
        # with the feature operation set on the writer
        # the def line is overspecified
        log.warning(
            tr(
                "The fme_db_operation attribute value '{db_op_val}' on feature "
                "conflicts with Feature Operation '{param_val}'"
            ).format(db_op_val=fme_db_operation_value, param_val=operation_type)
        )
        return None

    return operation_type


class OpenParameters(OrderedDict):
    """
    Provides convenient access to the open() parameters given to
    :meth:`FMEReader.open` and :meth:`FMEWriter.open`.

    Parameter keys that appear multiple times in the parameters list will result in
    values of type :class:`list`.
    This scenario is most likely to be encountered with `+ID` keys,
    though such keys are usually handled
    by :meth:`FMEMappingFile.fetchFeatureTypes` instead.

    :ivar str dataset: FME-decoded dataset value from the first argument to `open()`.
    :ivar list original: Original parameters passed to `open()`.
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
        self.dataset = self.__session.decodeFromFMEParsableText(dataset)

        self.original = parameters
        if len(parameters) >= 3:
            self.update(stringarray_to_dict(parameters, start=1))

    def get(self, key, default=None, decode=True):
        """Get an `open()` parameter.

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
        """Get an `open()` parameter and interpret its value as a boolean.

        :param str key: Key to look for.
        :param bool default: Value to return if key not present.
        :rtype: bool
        """
        value = self.get(key)
        if value is None:
            return default
        if isinstance(value, list):
            return False not in map(string_to_bool, value)
        return string_to_bool(value)

    def __str__(self):
        return "Open parameters: " + ", ".join(
            "%s: %s" % (key, value) for key, value in self.items()
        )


DefLine = namedtuple("DefLine", "feature_type attributes options")


SearchEnvelope = namedtuple("SearchEnvelope", "min_x min_y max_x max_y coordsys")


@dataclass
class UserAttributeInfo:
    attr_type: str
    attr_width: Optional[int] = None
    attr_precision: Optional[int] = None
    attr_index: Optional[str] = None


@dataclass
class FeatureTypeInfo:
    name: str
    user_attributes: Dict[str, UserAttributeInfo] = dataclasses.field(
        default_factory=dict
    )
    parameters: Dict = dataclasses.field(default_factory=dict)


class MappingFileDirectiveType(Enum):
    STRING = "STRING"
    NUMERIC = "NUMERIC"
    BOOL = "BOOL"


class Directives(dict):
    """
    Directives which can be populated by using a mapping file.
    Can be configured with expected directive types and defaults.
    """

    SUPPORTED_TYPES = {
        "ACTIVECHOICE_LOOKUP": MappingFileDirectiveType.STRING.value,
        "CHECKBOX": MappingFileDirectiveType.BOOL.value,
        "CHOICE": MappingFileDirectiveType.STRING.value,
        "FLOAT": MappingFileDirectiveType.NUMERIC.value,
        "INTEGER": MappingFileDirectiveType.NUMERIC.value,
        "LOOKUP_CHOICE": MappingFileDirectiveType.STRING.value,
        "NAMED_CONNECTION": MappingFileDirectiveType.STRING.value,
        "PASSWORD": MappingFileDirectiveType.STRING.value,
        "PASSWORD_CONFIRM": MappingFileDirectiveType.STRING.value,
        "RANGE_SLIDER": MappingFileDirectiveType.NUMERIC.value,
        "STRING": MappingFileDirectiveType.STRING.value,
        "TEXT_EDIT": MappingFileDirectiveType.STRING.value,
    }
    TYPE_DEFAULTS = {
        MappingFileDirectiveType.STRING.value: "",
        MappingFileDirectiveType.BOOL.value: False,
        MappingFileDirectiveType.NUMERIC.value: 0,
    }

    def __init__(
        self,
        directive_names: Set[str],
        directive_gui_types: Dict[str, str] = None,
        directive_defaults: Dict = None,
    ):
        super().__init__()
        self.names = directive_names
        if directive_gui_types is None:
            directive_gui_types = dict()

        if directive_defaults is None:
            directive_defaults = dict()

        self.directive_types = {}
        self.directive_defaults = {}
        for name in directive_names:
            gui_type = directive_gui_types.get(name)
            self.directive_types[name] = self._get_directive_type_from_gui_type(
                gui_type
            )

            if name in directive_defaults:
                self.directive_defaults[name] = directive_defaults[name]
            else:
                self.directive_defaults[name] = self._get_directive_default(
                    self.directive_types[name]
                )

    def _get_directive_type_from_gui_type(
        self, gui_type: str
    ) -> MappingFileDirectiveType:
        """Determine the :class:`fmetools.parsers.MappingFileDirectiveType` corresponding to the GUI type."""
        if gui_type is None:
            # default to GUI type STRING if no GUI type was explicitly specified
            gui_type = "STRING"
        parsed_gui_type = parse_gui_type(gui_type)

        # default to treating values as strings if the GUI type specified isn't a supported type
        return self.__class__.SUPPORTED_TYPES.get(
            parsed_gui_type.name, MappingFileDirectiveType.STRING.value
        )

    def _get_directive_default(self, directive_type: MappingFileDirectiveType):
        """
        Return a default value for the directive type.
        This is used when the corresponding directive is not found in the mapping file.
        """
        if directive_type in self.__class__.TYPE_DEFAULTS:
            return self.__class__.TYPE_DEFAULTS[directive_type]

        # directive type doesn't have a default set, return the default for STRING (or None)
        return self.__class__.TYPE_DEFAULTS.get(MappingFileDirectiveType.STRING.value)


class MappingFile:
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

    def __init__(
        self, mapping_file: FMEMappingFile, plugin_keyword: str, plugin_type: str
    ):
        """
        :param mapping_file: The original mapping file object.
        :param plugin_keyword: Plugin keyword string.
        :param plugin_type: The format short name, as specified in the metafile.
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

    def fetch_with_prefix(
        self, plugin_keyword: str, plugin_type: str, directive: str
    ) -> str:
        """Like :meth:`FMEMappingFile.fetchWithPrefix`, but also handles the
        Python-specific situation where directive values are returned as
        2-element lists with identical values.

        :param plugin_keyword: Plugin keyword string.
        :param plugin_type: Plugin type string.
        :param directive: Name of the directive.
        :return: If the value is scalar or a 2-element list with identical elements,
            return the element. Otherwise, the list is returned as-is.
        """
        value = self.mapping_file.fetchWithPrefix(
            plugin_keyword, plugin_type, directive
        )
        if isinstance(value, list) and len(value) == 2 and value[0] == value[1]:
            return value[0]
        return value

    def get(
        self,
        directive: str,
        *,
        default: Optional[str] = None,
        decode: bool = True,
        as_list: bool = False,
    ) -> Optional[Union[str, int, float, List]]:
        """
        Fetch a directive from the mapping file, assuming the given plugin
        keyword and type.

        :param directive: Name of the directive.
        :param default: Value to return if directive not present.
        :param decode: Whether to interpret the value as FME-encoded,
            and return the decoded value.
        :param as_list:  If true, then parse the value as a space-delimited list,
            and return a list.
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

    def get_flag(self, directive: str, default: bool = False) -> bool:
        """Get the specified directive and interpret it as a boolean value.

        :param str directive: Name of the directive.
        :param bool default: Value to return if directive not present.
        """
        value = self.get(directive)
        if value is None:
            return default

        return string_to_bool(value)

    def get_number(
        self, directive: str, default: Union[float, int] = 0
    ) -> Union[float, int]:
        """
        Get the specified directive and interpret it as a numeric value.

        :param directive: Name of the directive.
        :param default: Value to return if directive not present or non-numeric.
        """
        value = self.get(directive)
        if value is None:
            return default

        try:
            return float(value)
        except ValueError:
            return default

    def get_search_envelope(self) -> SearchEnvelope:
        """Get the search envelope, with coordinate system, if any.

        :returns: The search envelope, or None if not set.
        """
        env = self.mapping_file.fetchSearchEnvelope(
            self._plugin_keyword, self._plugin_type
        )
        if not env:
            return None
        coordsys = self.get("_SEARCH_ENVELOPE_COORDINATE_SYSTEM")
        return SearchEnvelope(env[0][0], env[0][1], env[1][0], env[1][1], coordsys)

    def get_feature_types(
        self, open_parameters: List[str], fetch_mode: str = "FETCH_IDS_AND_DEFS"
    ) -> List[str]:
        """Get the feature types, if any.

        :param open_parameters: Parameters for the reader.
        :param fetch_mode: `FETCH_IDS_AND_DEFS` or `FETCH_DEFS_ONLY`
        :returns: List of feature types.
        """
        featTypes = self.mapping_file.fetchFeatureTypes(
            self._plugin_keyword, self._plugin_type, open_parameters, fetch_mode
        )
        if featTypes is None:
            # Mapping file returns None when there are no feature types,
            # but that requires a separate check for None in code that uses it.
            # Eliminate this distinction.
            return []
        return [_system_to_unicode(ft) for ft in featTypes]

    def parse_def_lines(
        self, parameter_names: Set[str] = None
    ) -> Dict[str, FeatureTypeInfo]:
        """Return the user schema and feature type options for each feature type defined in the mapping file."""
        if not parameter_names:
            parameter_names = set()
        parameter_names.add("fme_attribute_reading")

        def_line_info = {}
        for def_line in self.def_lines():
            defline_feature_type, raw_attrs, def_line_params = parse_def_line(
                def_line, parameter_names
            )

            attrs = {}
            for attr_name, attr_type in raw_attrs.items():
                attrs[attr_name] = _parse_raw_attr_type(attr_type)

            def_line_info[defline_feature_type] = FeatureTypeInfo(
                defline_feature_type, attrs, def_line_params
            )

        return def_line_info

    def get_directives(self, directives: Directives) -> Directives:
        """Get cast directive values from the mapping file."""
        for name, gui_type in directives.directive_types.items():
            directive_default = directives.directive_defaults[name]
            if gui_type == MappingFileDirectiveType.STRING.value:
                # always decode, regardless of GUI value?
                directives[name] = self.get(name, default=directive_default)
            elif gui_type == MappingFileDirectiveType.NUMERIC.value:
                directives[name] = self.get_number(name, default=directive_default)
            elif gui_type == MappingFileDirectiveType.BOOL.value:
                directives[name] = self.get_flag(name, default=directive_default)
            else:
                directives[name] = self.get(name, default=directive_default)

        return directives


class ConstraintSearchTypes(Enum):
    """Potential search types supported by :meth:`fmetools.plugins.FMESimplifiedReader.setConstraints`."""

    def _generate_next_value_(name, start, count, last_values):
        # fme_ prefix all search types
        return f"fme_{name.lower()}"

    SEARCH_TYPE = auto()

    ALL_SCHEMAS = auto()
    ALL_FEATURES = auto()
    ENVELOPE_INTERSECTS = auto()
    ENVELOPE_IDS = auto()
    NONSPATIAL_IDS = auto()
    FEATURE_TYPE_IDS = auto()
    CLOSEST = auto()
    SPECIFIED_FEATURE = auto()
    SPECIFIED_FEATURE_LIST = auto()
    SPECIFIED_FEATURE_RANGE = auto()
    EXECUTE_SQL = auto()
    SCHEMA_FROM_QUERY = auto()
    DB_JOIN = auto()
    METADATA = auto()
    GET_VERSION_LIST = auto()
    GET_HISTORICAL_VERSION_LIST = auto()
    SPATIAL_INTERSECTION = auto()

    PROP_PERSISTENT_CACHE_LOADED = auto()
    PROP_PERSISTENT_CACHE_FEATURES_LOADED = auto()
    PROP_PERSISTENT_CACHE_SCHEMAS_LOADED = auto()
    PROP_PERSISTENT_CACHE_VALID = auto()

    PROP_COORD_SYS_AWARE = auto()
    PROP_SPATIAL_INDEX = auto()


class ConstraintsProperties:
    """
    Defines constraint types and associated constraint primitives.
    For use with :meth:`fmetools.plugins.FMESimplifiedReader.setConstraints`.
    """

    def __init__(self, **kwargs: Dict[ConstraintSearchTypes, List[str]]):
        self.properties = {
            e.value: kwargs.get(e.value)
            for e in ConstraintSearchTypes
            if kwargs.get(e.value) is not None
        }
        # if not specified, populate the fme_search_type property with a list of the other supported search types
        if ConstraintSearchTypes.SEARCH_TYPE.value not in self.properties:
            # ignore fme_prop_* as search types to support
            self.properties[ConstraintSearchTypes.SEARCH_TYPE.value] = [
                search_type
                for search_type in self.properties
                if not search_type.startswith("fme_prop_")
            ]

    @property
    def constraints_supported(self):
        return bool(self.properties)

    @staticmethod
    def _zip_properties(
        category: str, properties: Optional[List[str]]
    ) -> Generator[str, None, None]:
        """
        Given a single category and a list of corresponding properties,
        return a list where each odd index contains the category,
        and each even index is a property.

        Example:

           ``[category, property[0], category, property[1], ..., category, property[n]]``
        """
        if not properties:
            return None
        for property_name in properties:
            yield category
            yield property_name

    def _get_all_properties(self):
        all_properties = []
        for property_category, props in self.properties.items():
            all_properties.extend(list(self._zip_properties(property_category, props)))
        return all_properties

    def get_property_list(self, property_category: str) -> Optional[List[str]]:
        """
        Returns an even-length flat list of property category to constraint primitive pairs.
        If the property was not recognized, returns `None`.
        """
        if property_category == kFME_ReaderPropAll:
            # declare all supported constraints
            return self._get_all_properties()

        return (
            list(
                self._zip_properties(
                    property_category, self.properties.get(property_category, [])
                )
            )
            or None
        )

    def get_constraint_primitives(self, search_type: str) -> List[str]:
        """
        Returns a list of constraint primitives supported for the corresponding search type.
        """

        return self.properties.get(search_type, [])
