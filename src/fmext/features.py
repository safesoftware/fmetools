from collections import OrderedDict

import fmeobjects
from fmeobjects import FMEFeature
from six import iteritems


def build_feature(
    feature_type, attrs=None, attr_types=None, geometry=None, coord_sys=None
):
    """Build an :class:`fmeobjects.FMEFeature` instance with the most frequently used
    parameters.

    This helper function reduces verbosity and boilerplate code associated with
    FMEFeature construction.
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
