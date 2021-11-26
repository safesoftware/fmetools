# coding: utf-8

import math
import sys
from collections import OrderedDict

import pytest
from fmeobjects import FMEFeature, FME_BUILD_NUM, FMEPoint, FMENull
from hypothesis import given, settings
from hypothesis.strategies import (
    text,
    one_of,
    booleans,
    none,
    floats,
    integers,
    binary,
    dictionaries,
    lists,
    characters,
)

from fmetools.features import (
    set_attribute,
    get_attribute,
    set_attributes,
    get_attributes,
    get_attributes_with_prefix,
    set_list_attribute_with_properties,
    build_feature,
    build_schema_feature,
)

UTF8NAMES_SUPPORT = FME_BUILD_NUM >= 22000


@given(
    one_of(
        none(),
        booleans(),
        lists(
            one_of(integers(min_value=-sys.maxsize, max_value=sys.maxsize), text()),
            min_size=1,
            max_size=2,
        ),
        text(max_size=1),
        binary(max_size=1),
        integers(min_value=-sys.maxsize, max_value=sys.maxsize),
        floats(allow_infinity=False),
    ),
)
@settings(deadline=None)
def test_set_and_get_attribute_values(value):
    f = FMEFeature()
    set_attribute(f, "name", value)
    if isinstance(value, float) and math.isnan(value):
        assert math.isnan(get_attribute(f, "name"))
        return
    elif isinstance(value, list):
        if len(value) == 0:
            assert not [x for x in f.getAllAttributeNames() if x.startswith("name")]
        else:
            assert get_attribute(f, "name") == value
            for i, v in enumerate(value):
                assert get_attribute(f, "name{%s}" % i) == v
    else:
        assert get_attribute(f, "name") == value
        assert "name" in f.getAllAttributeNames()
    assert get_attribute(f, "name", pop=True) == value
    assert "name" not in f.getAllAttributeNames()
    assert get_attribute(f, "missing", default=value) == value


@given(characters(blacklist_categories=("C",)))
@settings(deadline=None)
def test_get_and_set_attribute_names(name):
    f = FMEFeature()
    set_attribute(f, name, "foo")
    assert get_attribute(f, name) == "foo"


def test_get_attributes_with_prefix():
    f = FMEFeature()
    set_attributes(f, {"prefix1_%s" % i: 1 for i in range(3)})
    set_attributes(f, {"prefix2_%s" % i: 1 for i in range(3)})
    assert len(get_attributes_with_prefix(f, "prefix1_")) == 3
    assert len(get_attributes_with_prefix(f, "prefix2_", pop=True)) == 3
    assert len(get_attributes_with_prefix(f, "prefix2_")) == 0


@given(dictionaries(text(min_size=1, max_size=1), text(min_size=1, max_size=1)))
@settings(deadline=None)
@pytest.mark.xfail(
    not UTF8NAMES_SUPPORT,
    reason="Unicode attribute names need FME >= 2022",
)
def test_set_and_get_attributes(attrs):
    f = FMEFeature()
    set_attributes(f, attrs)
    assert get_attributes(f, attrs.keys()) == attrs


def test_build_feature():
    f = build_feature("feattype", attrs={"foo": "bar"}, geometry=FMEPoint(1, 1, 1), coordsys="LL84")
    assert not f.getSequencedAttributeNames()
    assert f.getFeatureType() == "feattype"
    assert isinstance(f.getGeometry(), FMEPoint)
    assert f.getCoordSys() == "LL84"
    assert f.getAttribute("foo") == "bar"


def test_build_schema_feature():
    user_attrs = OrderedDict()
    user_attrs["user_attr_1"] = "fake_type_1"
    user_attrs["user_attr_2"] = "fake_type_2"
    geoms = ["foo", "bar"]
    f = build_schema_feature(
        "feattype",
        schema_attrs=user_attrs,
        fme_geometries=geoms,
    )
    assert f.getFeatureType() == "feattype"
    assert not f.getCoordSys()
    assert isinstance(f.getGeometry(), FMENull)
    assert f.getSequencedAttributeNames() == list(user_attrs.keys())
    assert f.getAttribute("fme_geometry") == geoms


def test_set_list_attribute_with_properties():
    f = FMEFeature()
    props = {"foo{}.bar": 1, "foo{}.baz": 1}
    set_list_attribute_with_properties(f, 10, props)
    assert get_attribute(f, "foo{10}.bar")
    assert get_attribute(f, "foo{10}.baz")
