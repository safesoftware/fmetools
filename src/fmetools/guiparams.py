"""
This module provides tools for working with FME GUI parameter values.
GUI parameter values are set as string attributes on features.
Depending on the GUI type that supplied the value,
these values may need to be parsed or deserialized.

Developers should only need to use :class:`GuiParameterParser`.
"""
from collections import namedtuple
from typing import Mapping, Union

from fmeobjects import FMEFeature, FMESession

from .features import get_attribute


class ParameterParser:
    def __init__(self, or_attr=False, encoded=False, config=None):
        self.or_attr = or_attr
        self.encoded = encoded
        self.config = config

    def __call__(self, value: Union[bool, int, float, str]):
        if isinstance(value, str) and self.encoded:
            return FMESession().decodeFromFMEParsableText(value)
        return value


class IntParser(ParameterParser):
    def __call__(self, value):
        if value == "":
            return None
        return int(super().__call__(value))


class FloatParser(ParameterParser):
    def __call__(self, value):
        if value == "":
            return None
        return float(super().__call__(value))


class BoolParser(ParameterParser):
    def __call__(self, value):
        value = super().__call__(value)
        if isinstance(value, str):
            return value.upper() not in {"FALSE", "F", "NO", "N", "", "0"}
        return bool(value)


class StringParser(ParameterParser):
    def __call__(self, value):
        value = super().__call__(value)  # supermethod handled FME decode
        if not isinstance(value, str):
            return str(value)
        return value


class FMEParsableStringParser(ParameterParser):
    """
    Like StringParser, but always FME-decodes.
    Note that setting ``encoded`` to true will result in double decoding.
    """

    def __call__(self, value):
        value = super().__call__(value)
        if not isinstance(value, str):
            return str(value)
        return FMESession().decodeFromFMEParsableText(value)


class ListParser(ParameterParser):
    """
    Parse a space-delimited list, with FME-encoded items.
    """

    def __call__(self, value):
        if isinstance(value, list):
            return value
        value = super().__call__(value)
        if not isinstance(value, str):
            return [str(value)]
        s = FMESession()
        items = list(map(s.decodeFromFMEParsableText, value.split()))
        if items == [""]:
            return []
        return items


SUPPORTED_TYPES = {
    "ACTIVECHOICE_LOOKUP": FMEParsableStringParser,
    "CHECKBOX": BoolParser,
    "CHOICE": FMEParsableStringParser,
    "FLOAT": FloatParser,
    "INTEGER": IntParser,
    "LISTBOX": ListParser,
    "LOOKUP_LISTBOX": ListParser,
    "LOOKUP_CHOICE": FMEParsableStringParser,
    "NAMED_CONNECTION": StringParser,
    "PASSWORD": StringParser,
    "PASSWORD_CONFIRM": StringParser,
    "RANGE_SLIDER": FloatParser,
    "STRING": StringParser,
    "TEXT_EDIT": FMEParsableStringParser,
}


GuiType = namedtuple("GuiType", "name or_attr encoded config")


def parse_gui_type(gui_type: str):
    try:
        gui_type, config = gui_type.split(" ", maxsplit=1)
    except ValueError:
        config = None
    or_attr = "_OR_ATTR" in gui_type
    encoded = "_ENCODED" in gui_type
    gui_type = gui_type.replace("_OR_ATTR", "").replace("_ENCODED", "")
    return GuiType(gui_type, or_attr, encoded, config)


def get_parser(gui_type: str):
    """
    Get a configured GUI parameter deserializer instance for the given GUI type.

    :param gui_type: GUI type name, including any suffixes and config.
        e.g. ``TEXT_EDIT_OR_ATTR ``.
    """
    parts = parse_gui_type(gui_type)
    try:
        return SUPPORTED_TYPES[parts.name](
            or_attr=parts.or_attr, encoded=parts.encoded, config=parts.config
        )
    except KeyError as e:
        raise KeyError(
            "unrecognized or unsupported GUI type '{}'".format(parts.name)
        ) from e


_default = object()


class GuiParameterParser:
    def __init__(self, gui_params: Mapping[str, str]):
        """
        Helper for deserializing FME GUI parameter values.

        This initial implementation supports just a small subset of GUI types.

        :param gui_params: Mapping of GUI parameter attribute name to its GUI type.
        :raises KeyError: if an unrecognized/unsupported GUI type is specified.
        """
        self.parsers = {}
        for attr_name, gui_type in gui_params.items():
            self.parsers[attr_name] = get_parser(gui_type)

    def get(self, feature: FMEFeature, attr_name: str, default=None):
        """
        :param feature: Get the GUI parameter value from this feature.
        :param attr_name: Attribute name of the GUI parameter.
        :param default: Return this value if the attribute is missing.
        :raises KeyError: if ``attr_name`` wasn't an attribute specified in the constructor.
        :raises ValueError: if there was a problem parsing the value.
        :returns: The parsed GUI parameter value, or default if missing.
            Always returns ``None`` if the parameter value was ``None``.
        """
        parser = self.parsers[attr_name]
        value = get_attribute(feature, attr_name, default=_default)
        if value is None:
            return None
        if value is _default:
            return default
        try:
            return parser(value)
        except KeyError as e:
            raise KeyError(
                "GUI parameter attribute '{}' not registered".format(attr_name)
            ) from e
