# coding: utf-8
"""
This module contains :class:`fmeobjects.FMEFeature` utilities for getting attributes, setting attributes,
and building complete features.
These utilities make it more convenient to work with FMEFeature objects,
and help avoid common errors.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from fmeobjects import FME_ATTR_STRING, FMEFeature, FMEGeometry, kFMERead_Geometry

from . import tr


def set_attribute(
    feature: FMEFeature, name: str, value: Any, attr_type: Optional[int] = None
) -> None:
    """
    Set an attribute onto a feature, with null value handling.

    :param feature: Feature to set attribute on.
    :param name: Attribute name.
    :param value: Value to set.
    :param attr_type: Intended attribute type, used when the value is ``None``.
        Default is :data:`fmeobjects.FME_ATTR_STRING`.
    """
    if value is None:
        # FME_ATTR_UNDEFINED is silently interpreted as FME_ATTR_STRING.
        feature.setAttributeNullWithType(name, attr_type or FME_ATTR_STRING)
    else:
        feature.setAttribute(name, value)


def set_attributes(
    feature: FMEFeature,
    attrs: dict[str, Any],
    attr_types: Optional[dict[str, int]] = None,
) -> None:
    """
    Set attributes onto a feature, with null value handling.

    :param feature: Feature to set attributes on.
    :param attrs: Attribute names and values.
    :param attr_types: Attribute names and their fmeobjects type.
        This is used for setting null attribute values.
        If not specified, or if there's no mapping for a given attribute name,
        then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    """
    attr_types = attr_types or {}
    for name, value in attrs.items():
        set_attribute(feature, name, value, attr_types.get(name))


_HAS_NULL_VALUE_METHOD = "isAttributeNull" in FMEFeature.__dict__


def get_attribute(
    feature: FMEFeature, attr_name: str, default: Any = None, pop: bool = False
) -> Any:
    """
    Get one attribute from a feature.

    :param feature: Feature to get an attribute from.
    :param attr_name: Attribute to get.
    :param default: If the attribute is missing, then return this value.
    :param pop: Whether the attribute is to be deleted from the feature.
    """
    value = feature.getAttribute(attr_name)
    if value is None:
        if pop:
            feature.removeAttribute(attr_name)
        return default  # Always means the attribute is missing.
    if value == "":
        if _HAS_NULL_VALUE_METHOD:
            is_null = feature.isAttributeNull(attr_name)
        else:
            is_null = feature.getAttributeNullMissingAndType(attr_name)[0]
        if is_null:
            value = None
    if pop:
        feature.removeAttribute(attr_name)
    return value


def get_attributes(
    feature: FMEFeature,
    attr_names: Iterable[str],
    default: Any = None,
    pop: bool = False,
) -> dict[str, Any]:
    """
    Get multiple attributes from a feature.

    :param feature: Feature to get attributes from.
    :param attr_names: Attributes to get.
    :param default: If the attribute isn't present, then use this value.
    :param pop: Whether the attributes are to be deleted from feature.
    """
    return {
        name: get_attribute(feature, name, default=default, pop=pop)
        for name in attr_names
    }


def get_attributes_with_prefix(
    feature: FMEFeature, prefix: str, default: Any = None, pop: bool = False
) -> dict[str, Any]:
    """
    Get attributes with names that start with a given prefix.

    :param feature: Feature to get attributes from.
    :param prefix: Get attributes with names that start with this prefix.
    :param default: If the attribute isn't present, then use this value.
    :param pop: Whether the attributes are to be deleted from feature.
    """
    return get_attributes(
        feature,
        filter(lambda x: x.startswith(prefix), feature.getAllAttributeNames()),
        default=default,
        pop=pop,
    )


def build_feature(
    feature_type: str,
    attrs: dict[str, Any] = None,
    attr_types: Optional[dict[str, int]] = None,
    geometry: Optional[FMEGeometry] = None,
    coordsys: Optional[str] = None,
) -> FMEFeature:
    """
    Build an :class:`~fmeobjects.FMEFeature` instance with the most frequently used parameters.

    This function simplifies the process of building a feature.
    This helps avoid common errors such as:

    * Undefined geometry on feature
    * Calling :meth:`fmeobjects.FMEFeature.setAttribute` with a ``None`` value

    To build schema features, use :func:`build_schema_feature` instead.

    :param feature_type: The feature type.
    :param attrs: Attribute names and values.
    :param attr_types: Attribute names and their fmeobjects type.
        This is used for setting null attribute values.
        If not specified, or if there's no mapping for a given attribute name,
        then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    :param geometry: Geometry to put on the feature.
    :param coordsys: Coordinate system name to set.
    """
    feature = FMEFeature()
    feature.setFeatureType(feature_type)
    feature.setGeometry(geometry)
    if coordsys:
        feature.setCoordSys(coordsys)
    set_attributes(feature, attrs, attr_types)
    return feature


def build_schema_feature(
    feature_type: str,
    schema_attrs: Optional[dict[str, str]] = None,
    fme_geometries: Optional[list[str]] = None,
) -> FMEFeature:
    """
    Build an :class:`~fmeobjects.FMEFeature` suitable for returning from
    :meth:`pluginbuilder.FMEReader.readSchema`.
    This helps avoid common errors such as:

    * Setting any geometry on the feature
    * Setting non-user attributes as sequenced attributes
    * Setting user attributes as regular attributes

    :param feature_type: The feature type.
    :param schema_attrs:
        Ordered schema attributes for the feature type. Key order is important.
        Keys are attribute names, and values are format-specific attribute types.
    :param fme_geometries:
        Format-specific geometry type names for this feature type.
    """
    if schema_attrs is None:
        schema_attrs = {}

    feature = FMEFeature()
    feature.setFeatureType(feature_type)
    if fme_geometries:
        feature.setAttribute(kFMERead_Geometry, fme_geometries)

    for attr_name, value in schema_attrs.items():
        assert value
        feature.setSequencedAttribute(attr_name, value)

    return feature


def set_list_attribute_with_properties(
    feature: FMEFeature,
    index: int,
    property_attrs: dict[str, Any],
    attr_types: Optional[dict[str, int]] = None,
) -> None:
    """
    Set a list attribute entry onto a feature, where the entry consists
    of one or more properties, e.g.: ``name{i}.property``.

    To set a regular list attribute without properties,
    use :meth:`fmeobjects.FMEFeature.setAttribute` or :func:`set_attribute`.

    :param feature: Feature to receive the list attribute.
    :param index: Index into the list attribute to set.
    :param property_attrs: List attribute names and values.
        All attribute names must follow the format ``name{}.property``.
        The empty braces will get filled with the index.
    :param attr_types: Attribute names and their fmeobjects type.
        This is used for setting null attribute values.
        If not specified, or if there's no mapping for a given attribute name,
        then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    """
    attr_types = attr_types or {}
    for attr_name, value in property_attrs.items():
        if "{}" not in attr_name:
            raise ValueError(tr("List attribute name missing '{}'"))
        final_attr_name = attr_name.replace("{}", "{%s}" % index, 1)
        set_attribute(feature, final_attr_name, value, attr_types.get(attr_name))
