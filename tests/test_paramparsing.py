import fmeobjects
import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from fmetools.features import build_feature

# Allow this test to skip gracefully with pytestmark, if import fails.
try:
    from fmetools.paramparsing import TransformerParameterParser, _FME_NULL_VALUE
except ModuleNotFoundError:
    pass


pytestmark = pytest.mark.skipif(
    fmeobjects.FME_BUILD_NUM < 23224, reason="Requires FME >= b23224"
)


@pytest.fixture
def creator():
    return TransformerParameterParser("Creator", version=6)


def test_system_transformer(creator):
    t = creator
    # Get params with defaults from transformer def
    assert t["NUM"] == 1  # INTEGER type gives int
    assert t["CRE_ATTR"] == "_creation_instance"
    assert t.is_required("NUM")

    assert not t.is_required("COORDSYS")  # Enabled but optional
    assert t["COORDSYS"] == ""  # Default value is empty string
    # Set and get a param
    t.set("COORDSYS", "LL84")
    assert t["COORDSYS"] == "LL84"

    # Invalid type for name
    with pytest.raises(TypeError) as e:
        t.set(1, 1)  # noqa
    assert "must be str, failed to get string value" in str(e.value)

    # This doesn't clear default values
    assert t.set_all({})
    assert t["NUM"] == 1

    # Unparsed value being an int is okay if the param type is also int
    for val in [2, "2"]:
        t["NUM"] = val
        assert t["NUM"] == 2

    # This doesn't clear set values either, so set_all() with empty dict is a no-op
    assert t.set_all({})
    assert t["NUM"] == 2

    # TODO: Add test for conditionally hidden fields, which are possible in FMXJ


def check_disabled_param_access(xformer, param_name):
    if fmeobjects.FME_BUILD_NUM >= 25759:  # FMEFORM-34668 (see comments)
        with pytest.raises(ValueError) as exc:
            assert not xformer[param_name]
        # TODO: Message to be improved by FOUNDATION-8506.
        assert "parameter value does not match the parameter type" in str(exc.value)
    else:
        assert not xformer[param_name]  # Exists but disabled so no KeyError


def test_simple_dependent_params(creator):
    # Test dependent parameters behaviour (conditionally enabled/disabled):
    # GEOMTYPE is ACTIVECHOICE involving GEOM and COORDS.
    # Check default values, then change GEOMTYPE and see its
    # dependent parameters get enabled/disabled with values.
    t = creator
    # When GEOMTYPE is "Geometry Object", GEOM is enabled and COORDS is disabled.
    assert t["GEOMTYPE"] == "Geometry Object"
    assert t.is_required("GEOM")
    assert t["GEOM"].startswith("<?xml")  # FME-decoded too
    assert not t.is_required("COORDS")
    check_disabled_param_access(t, "COORDS")

    # Change GEOMTYPE to "2D Coordinate List". GEOM is disabled, COORDS enabled.
    t.set("GEOMTYPE", "2D Coordinate List")
    assert not t.is_required("GEOM")  # Now disabled
    check_disabled_param_access(t, "GEOM")
    assert t.is_required("COORDS")  # Now enabled
    t["COORDS"] = "LL84"
    assert t["COORDS"] == "LL84"

    # When dependency is set to a bad value, both dependents are enabled.
    t.set("GEOMTYPE", "invalid")
    assert t["GEOMTYPE"] == "invalid"  # Allowed
    assert t.is_required("GEOM")  # Enabled again
    assert t["GEOM"].startswith("<?xml")  # Its default value is retrievable
    assert t.is_required("COORDS")  # Enabled again
    assert (
        t["COORDS"] == "LL84"
    )  # And it kept the value set before the bad dependency state


def test_nonexistent_param(creator):
    """Get and set a non-existent parameter."""
    # Set a non-existent parameter, should not raise an error
    assert creator.set("NON_EXISTENT", "value")
    # But trying to get it back will raise.
    with pytest.raises(KeyError):
        creator.get("NON_EXISTENT", prefix=None)

    with pytest.raises(KeyError):
        creator.get("NUM")  # ___XF_NUM doesn't exist


@pytest.mark.parametrize(
    "set_all_kwargs",
    [
        {"param_attr_names": ["NUM"]},
        {"param_attr_names": ["NUM", "CRE_ATTR"]},
        {"param_attr_names": ["NUM"], "param_attr_prefix": "CRE_"},
    ],
)
def test_partial_params_on_feature(creator, set_all_kwargs):
    """Set parameters from a feature that only has some of them."""
    f = build_feature(
        "foo",
        {
            "NUM": "10",  # str intentional
            # CRE_ATTR not provided, should get default
        },
    )
    assert creator.set_all(f, **set_all_kwargs)
    assert creator["NUM"] == 10  # Deserialized to int
    assert creator["CRE_ATTR"] == "_creation_instance"  # Default value


def test_partial_params_cache_staleness(creator):
    """
    Start with a feature that's missing a parameter attribute.
    Getting it returns the default from the transformer definition.
    Then supply a feature that has a value for the parameter attribute.
    Getting it returns the expected new value.
    Then supply a feature that's missing the parameter attribute again.
    Getting it should return the previously seen value, not the default again.
    """
    previous = "_creation_instance"
    for attrs in [
        {"NUM": "10"},
        {"NUM": "20", "CRE_ATTR": "_custom_creation_attr"},
        {"NUM": "30"},
    ]:
        f = build_feature("foo", attrs)
        assert creator.set_all(f, param_attr_names=["NUM", "CRE_ATTR"])
        assert creator["NUM"] == int(attrs["NUM"])
        previous = attrs.get("CRE_ATTR", previous)
        assert creator["CRE_ATTR"] == previous


def test_unparseable_as_int(creator):
    """Set a parameter to a value that cannot be parsed as an int, and try to get its parsed value."""
    # Set NUM to a string that cannot be parsed as an int
    assert creator.set("NUM", "not an int")
    with pytest.raises(ValueError):
        assert creator["NUM"]


@pytest.mark.parametrize(
    "transformer_info,param",
    [
        ("Creator 6", "NUM"),  # INTEGER
        (
            "StringReplacer 5",
            "NO_MATCH",
        ),  # OPTIONAL NULLABLE NO_OP STRING_ENCODED_OR_ATTR
    ],
)
def test_null_value(transformer_info, param):
    """Set and get a parameter with the "FME_NULL_VALUE" string. Verify that's returned as None."""
    name, version = transformer_info.split()
    xformer = TransformerParameterParser(name, version=int(version))
    assert xformer.set(param, _FME_NULL_VALUE)
    assert xformer[param] is None


@pytest.mark.parametrize("null_value", [_FME_NULL_VALUE, None])
def test_fmetransformer_null_value(null_value):
    """
    Test `fmeobjects.FMETransformer` behaviour around set/get of null values.

    - "FME_NULL_VALUE" is handled like any other string literal. It's not a sentinel value for null.
    - `None` is intercepted by `fmeobjects.FMETransformer` to ensure round-trip `None` behaviour.
    - `TransformerParameterParser` setters intentionally don't convert `None` or "FME_NULL_VALUE".
    - `TransformerParameterParser` getters intercept "FME_NULL_VALUE" to return `None` without asking `FMETransformer`.
    """
    xformer = fmeobjects.FMETransformer("StringReplacer", "", 6)
    assert xformer.getParsedParamValue("NO_MATCH") == "_FME_NO_OP_"  # default value
    assert xformer.setParameterValue("NO_MATCH", null_value)
    assert xformer.getParsedParamValue("NO_MATCH") == null_value
    assert xformer.setParameterValues({"NO_MATCH": null_value})
    assert xformer.getParsedParamValue("NO_MATCH") == null_value


@pytest.mark.xfail(fmeobjects.FME_BUILD_NUM < 25158, reason="FMEFORM-32592")
def test_empty_optional_int():
    t = TransformerParameterParser("VertexCreator", version=5)
    # FIXME: Ideally, empty optional int returns None. (FMEENGINE-34561)
    # Test initial state, then state after explicitly setting it to empty string,
    # which is how an empty default is represented on the feature.
    assert t["ZVAL"] == ""  #  OPTIONAL FLOAT_OR_ATTR, empty default
    t["ZVAL"] = ""
    assert t["ZVAL"] == ""
    # Before b25158:
    # ValueError: parameter value does not match the parameter type


@pytest.mark.xfail(
    condition=fmeobjects.FME_BUILD_NUM < 25754,
    reason="FMEFORM-34573: API incorrectly returns size 1 list with unparsed input string",
)
def test_listbox_or_multichoice():
    f = TransformerParameterParser("GoogleDriveConnector")
    assert f["_UPLOAD_FME_ATTRIBUTES_TO_ADD"]  # default isn't empty
    assert f["_UPLOAD_FME_ATTRIBUTES_TO_ADD"] == [
        "_sharable_link",
        "_direct_download_link",
        "_id",
    ]


def test_params_from_feature(creator):
    # Get parameters from an input feature.
    # Creator doesn't use attr prefixes. Provide list of internal param attr names.
    f = build_feature(
        "foo",
        {
            "NUM": "5",  # str intentional
        },
    )
    assert creator.set_all(f, param_attr_names=["NUM"])
    assert creator["NUM"] == 5  # Deserialized to int


def test_dict_access(creator):
    creator["NUM"] = "5"
    assert creator["NUM"] == 5
    with pytest.raises(NotImplementedError):
        del creator["NUM"]
    with pytest.raises(KeyError):
        assert creator["foo"]
    with pytest.raises(TypeError):
        assert creator[1]


@given(name=st.one_of(st.text()))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_invalid_param_name(name, creator):
    assert creator.set(name, 1)  # Returns true even for unrecognized names
    with pytest.raises(KeyError):
        creator.get("foo", prefix=None)


@pytest.mark.parametrize(
    "name,version",
    [
        ("Foo", 1),
        ("Creator", 0),
        ("Creator", 1),  # Not defined for Creator
    ],
)
def test_transformer_not_found(name, version):
    with pytest.raises(ValueError):
        TransformerParameterParser(name, version)


def test_versions():
    with pytest.raises(TypeError):
        TransformerParameterParser("Creator", "non int version")  # noqa

    t = TransformerParameterParser("Creator")
    # Version 2 added NUM. It's also the oldest defined version.
    assert t.get("NUM", prefix=None) == 1

    # Creator has no v1
    assert t.get("NUM", prefix=None) == 1
    # TransformerParameterParser init w/o version returns the latest version,
    # and latest version still has COORDSYS.
    assert t.set("COORDSYS", "LL84")
    assert t["COORDSYS"] == "LL84"

    # Version 4 added COORDSYS
    # When on an older version, setting a value for it is ignored.
    # Recall that change_version() recreates FMETransformer, so state isn't saved.
    t.change_version(3)
    assert t.set("COORDSYS", "LL84")
    with pytest.raises(KeyError):
        t.get("COORDSYS", prefix=None)
    t.change_version(4)
    assert t.get("COORDSYS", prefix=None) == ""
    assert t.set("COORDSYS", "LL84")
    assert t.get("COORDSYS", prefix=None) == "LL84"

    # Set a param that doesn't exist, and get it
    t.set("foo", "bar")
    with pytest.raises(KeyError):
        t.get("foo", prefix=None)
