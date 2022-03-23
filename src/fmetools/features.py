# coding: utf-8

"""
Utilities for working with :class:`FMEFeature`.
"""
from collections import OrderedDict

import fmeobjects
from fmeobjects import FMEFeature, kFMERead_Geometry, FME_ATTR_STRING
from six import iteritems
from . import tr


def set_attribute(feature, name, value, attr_type=None):
    """
    Set an attribute onto a feature, with null value handling.

    :type feature: FMEFeature
    :param str name: Attribute name.
    :param value: Value to set.
    :param int attr_type: Intended attribute type, used when the value is `None`.
        Default is `fmeobjects.FME_ATTR_STRING`.
    """
    if value is None:
        # FME_ATTR_UNDEFINED is silently interpreted as FME_ATTR_STRING.
        feature.setAttributeNullWithType(name, attr_type or FME_ATTR_STRING)
    else:
        feature.setAttribute(name, value)


def set_attributes(feature, attrs, attr_types=None):
    """
    Set attributes onto a feature, with null value handling.

    :type feature: FMEFeature
    :param dict attrs: Attribute names and values.
    :param dict attr_types: Attribute names and their fmeobjects type.
        This is used for setting null attribute values.
        If not specified, or if there's no mapping for a given attribute name,
        then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    """
    attr_types = attr_types or {}
    for name, value in iteritems(attrs or {}):
        set_attribute(feature, name, value, attr_types.get(name))


_HAS_NULL_VALUE_METHOD = "isAttributeNull" in FMEFeature.__dict__


def get_attribute(feature, attr_name, default=None, pop=False):
    """
    Get an attribute from a feature.

    :param FMEFeature feature: Feature to get an attribute from.
    :param str attr_name: Attribute to get.
    :param default: If the attribute is missing, then return this value.
    :param bool pop: Whether the attribute is to be deleted from feature.
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


def get_attributes(feature, attr_names, default=None, pop=False):
    """
    Get attributes from a feature.

    :param FMEFeature feature: Feature to get attributes from.
    :param Iterable attr_names: Attributes to get.
    :param default: If the attribute isn't present, then use this value.
    :param bool pop: Whether the attributes are to be deleted from feature.
    :rtype: dict
    """
    return {
        name: get_attribute(feature, name, default=default, pop=pop)
        for name in attr_names
    }


def get_attributes_with_prefix(feature, prefix, default=None, pop=False):
    """
    Get attributes that start with a given prefix.

    :param FMEFeature feature: Feature to get attributes from.
    :param str prefix: Attributes to get.
    :param default: If the attribute isn't present, then use this value.
    :param bool pop: Whether the attributes are to be deleted from feature.
    :rtype: dict
    """
    return get_attributes(
        feature,
        filter(lambda x: x.startswith(prefix), feature.getAllAttributeNames()),
        default=default,
        pop=pop,
    )


def build_feature(
    feature_type, attrs=None, attr_types=None, geometry=None, coordsys=None
):
    """
    Build an :class:`FMEFeature` instance with the most frequently used parameters.

    This helper function simplifies the process of building a feature.
    This helps avoid common errors such as:

    * Undefined geometry on feature
    * Calling :meth:`FMEFeature.setAttribute` with a `None` value

    To build schema features, use :func:`build_schema_feature` instead.

    :param str feature_type: The feature type.
    :param dict attrs: Attribute names and values.
    :param dict attr_types: Attribute names and their fmeobjects type.
        This is used for setting null attribute values.
        If not specified, or if there's no mapping for a given attribute name,
        then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    :param fmeobjects.FMEGeometry geometry: Geometry to put on the feature.
    :param str coordsys: Coordinate system name to set.
    :rtype: FMEFeature
    """
    feature = FMEFeature()
    feature.setFeatureType(feature_type)
    feature.setGeometry(geometry)
    if coordsys:
        feature.setCoordSys(coordsys)
    set_attributes(feature, attrs, attr_types)
    return feature


def build_schema_feature(feature_type, schema_attrs=None, fme_geometries=None):
    """
    Build an :class:`FMEFeature` suitable for returning from
    :meth:`pluginbuilder.FMEReader.readSchema`.
    This helps avoid common errors such as:

    * Setting any geometry on the feature
    * Setting non-user attributes as sequenced attributes
    * Setting user attributes as regular attributes

    :param str feature_type: The feature type.
    :param OrderedDict schema_attrs:
        Ordered schema attributes for the feature type.
        Keys are attribute names, and values are format-specific attribute types.
    :param list[str] fme_geometries:
        Format-specific geometry types for this feature type.
    :rtype: FMEFeature
    """
    assert isinstance(schema_attrs, OrderedDict) or not schema_attrs
    if schema_attrs is None:
        schema_attrs = {}

    feature = FMEFeature()
    feature.setFeatureType(feature_type)
    if fme_geometries:
        feature.setAttribute(kFMERead_Geometry, fme_geometries)

    for attr_name, value in iteritems(schema_attrs):
        assert value
        feature.setSequencedAttribute(attr_name, value)

    return feature


def set_list_attribute_with_properties(feature, index, property_attrs, attr_types=None):
    """
    Set a list attribute entry onto a feature, where the entry is comprised
    of one or more properties, e.g.: ``name{i}.property``.

    To set a property-less list attribute, use :meth:`FMEFeature.setAttribute`
    or :func:`set_attribute`.

    :param FMEFeature feature: Feature to receive the list attribute.
    :param int index: Index into the list attribute to set.
    :param dict property_attrs: List attribute names and values.
        All attribute names must follow the format ``name{}.property``.
        The empty braces will get filled with the index.
    :param dict attr_types: Attribute names and their fmeobjects type.
        This is used for setting null attribute values.
        If not specified, or if there's no mapping for a given attribute name,
        then the null value will be set with :data:`fmeobjects.FME_ATTR_STRING`.
    """
    attr_types = attr_types or {}
    for attr_name, value in iteritems(property_attrs):
        if "{}" not in attr_name:
            raise ValueError(tr("List attribute name missing '{}'"))
        final_attr_name = attr_name.replace("{}", "{%s}" % index, 1)
        set_attribute(feature, final_attr_name, value, attr_types.get(attr_name))
