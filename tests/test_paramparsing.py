import inspect
from enum import Enum

import fmeobjects
import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from fmetools.features import build_feature

# Allow this test to skip gracefully with pytestmark, if import fails.
try:
    from fmetools.paramparsing import ParameterState, TransformerParameterParser
except ModuleNotFoundError:
    pass


BUILD_NUM = fmeobjects.FME_BUILD_NUM
pytestmark = pytest.mark.skipif(BUILD_NUM < 23224, reason="Requires FME >= b23224")
FOUNDATION_8710 = 26036
"""Build where null integers return "FME_NULL_VALUE" instead of raising ValueError."""
FMEFORM_34573 = 25754
"""Build where list parameter parsing was fixed."""
FMEFORM_32592 = 25158
"""Build where empty optional int parameters return empty string instead of raising ValueError."""


MISSING = "MISSING"
SAME = "SAME"


# For the test cases below:
# - MISSING means to set no value, i.e. get the default from the transformer definition.
# - SAME means to copy the test parameter value from the left. This is to reduce duplication.
@pytest.mark.parametrize(
    "target,input_value,expected_value,expected_from_fmeobjects",
    [
        pytest.param("Creator 6 NUM", MISSING, 1, SAME, id="default int"),
        pytest.param("Creator 6 NUM", 2, SAME, SAME, id="set int, get int"),
        pytest.param("Creator 6 NUM", "2", 2, SAME, id="set str int, get int"),
        pytest.param("Creator 6 NUM", "FOO", ValueError, SAME, id="unparseable as int"),
        pytest.param(
            "Creator 6 CRE_ATTR", MISSING, "_creation_instance", SAME, id="default str"
        ),
        pytest.param(
            "Creator 6 COORDSYS", MISSING, "", SAME, id="default empty optional str"
        ),
        pytest.param("Creator 6 COORDSYS", "LL84", SAME, SAME, id="str"),
        pytest.param(
            "Creator 6 NONEXISTENT",
            "foo",
            KeyError,
            SAME,
            id="nonexistent param",
        ),
        pytest.param(
            "VertexCreator 6 ZVAL",
            MISSING,
            ValueError,
            SAME,
            id="default empty optional int < b25158",
            marks=pytest.mark.skipif(
                BUILD_NUM >= FMEFORM_32592, reason="changed by FMEFORM-32592"
            ),
        ),
        pytest.param(
            "VertexCreator 6 ZVAL",
            "",
            ValueError,
            SAME,
            id="empty optional int < b25158",
            marks=pytest.mark.skipif(
                BUILD_NUM >= FMEFORM_32592, reason="changed by FMEFORM-32592"
            ),
        ),
        pytest.param(
            "VertexCreator 6 ZVAL",
            MISSING,
            "",
            "",
            id="default empty optional int < b25795",
            marks=pytest.mark.skipif(
                25795 <= BUILD_NUM < 26000 or 26016 <= BUILD_NUM,
                reason="changed by FOUNDATION-8502",
            ),
        ),
        pytest.param(
            "VertexCreator 6 ZVAL",
            "",
            "",
            "",
            id="empty optional int < b25795",
            marks=pytest.mark.skipif(
                25795 <= BUILD_NUM < 26000 or 26016 <= BUILD_NUM,
                reason="changed by FOUNDATION-8502",
            ),
        ),
        pytest.param(
            "VertexCreator 6 ZVAL",
            MISSING,
            None,
            None,
            id="default empty optional int >= b25795",
            marks=pytest.mark.skipif(
                BUILD_NUM < 25795 or 26000 <= BUILD_NUM < 26016,
                reason="returns empty str before FOUNDATION-8502",
            ),
        ),
        pytest.param(
            "VertexCreator 6 ZVAL",
            "",
            None,
            None,
            id="empty optional int < b25795",
            marks=pytest.mark.skipif(
                BUILD_NUM < 25795 or 26000 <= BUILD_NUM < 26016,
                reason="returns empty str before FOUNDATION-8502",
            ),
        ),
        pytest.param(
            "GoogleDriveConnector 3 _UPLOAD_FME_ATTRIBUTES_TO_ADD",
            MISSING,
            ["_sharable_link _direct_download_link _id"]
            if BUILD_NUM < FMEFORM_34573
            else ["_sharable_link", "_direct_download_link", "_id"],
            SAME,
            id="default list",
        ),
        pytest.param(
            "GoogleDriveConnector 3 _UPLOAD_FME_ATTRIBUTES_TO_ADD",
            "",
            [] if BUILD_NUM >= FMEFORM_34573 else [""],
            SAME,
            id="empty list",
        ),
        pytest.param(
            "StringReplacer 6 NO_MATCH",
            MISSING,
            ParameterState.NO_OP,
            "_FME_NO_OP_",
            id="default no-op",
        ),
        pytest.param(
            "StringReplacer 6 NO_MATCH",
            "_FME_NO_OP_",
            ParameterState.NO_OP,
            "_FME_NO_OP_",
            id="no-op",
        ),
        pytest.param(
            "StringReplacer 6 NO_MATCH",
            "FME_NULL_VALUE",
            ParameterState.NULL,
            "FME_NULL_VALUE",
            id="FME_NULL_VALUE on nullable",
        ),
        pytest.param(
            "StringReplacer 6 NO_MATCH",
            None,
            ParameterState.NULL,
            None,
            id="None on nullable",
        ),
        pytest.param(
            "Creator 6 NUM",
            "FME_NULL_VALUE",
            ParameterState.NULL,
            ValueError if BUILD_NUM < FOUNDATION_8710 else "FME_NULL_VALUE",
            id="FME_NULL_VALUE on not nullable int",
        ),
        pytest.param(
            "KMLStyler 3 FILL_OPACITY",
            "FME_NULL_VALUE",
            ParameterState.NULL,
            ValueError if BUILD_NUM < FOUNDATION_8710 else "FME_NULL_VALUE",
            id="FME_NULL_VALUE on not nullable optional int",
        ),
        pytest.param(
            "Creator 6 CRE_ATTR",
            ParameterState.NULL,
            ParameterState.NULL,
            "FME_NULL_VALUE",
            id="FME_NULL_VALUE on not nullable optional str",
        ),
        pytest.param(
            "GoogleDriveConnector 3 _UPLOAD_FME_ATTRIBUTES_TO_ADD",
            "FME_NULL_VALUE",
            ParameterState.NULL,
            ["FME_NULL_VALUE"],
            id="FME_NULL_VALUE on not nullable list",
        ),
        pytest.param(
            "ExpressionEvaluator 3 NULL_ATTR_VALUE",
            "FME_NULL_VALUE",
            ParameterState.NULL,
            ValueError if BUILD_NUM < FOUNDATION_8710 else "FME_NULL_VALUE",
            id="FME_NULL_VALUE on nullable int",
        ),
        pytest.param(
            "ExpressionEvaluator 3 NULL_ATTR_VALUE",
            None,
            ParameterState.NULL,
            None,
            id="None on nullable int",
        ),
        pytest.param(
            "safe.test.NullTester 1 ___XF_NUMBER",
            MISSING,
            ParameterState.NULL,
            "FME_NULL_VALUE",
            id="default null int represented as FME_NULL_VALUE, not None",
            marks=pytest.mark.skip(
                "No shipped transformer with default null param value"
            ),
        ),
        pytest.param(
            "Creator 6 NUM",
            None,
            ParameterState.NULL,
            None,
            id="None round-trip on not nullable int",
        ),
        pytest.param(
            "Creator 6 CRE_ATTR",
            None,
            ParameterState.NULL,
            None,
            id="None round-trip on not nullable str",
        ),
        pytest.param(
            "StringReplacer 6 NO_MATCH",
            None,
            ParameterState.NULL,
            None,
            id="None round-trip on nullable str",
        ),
    ],
)
def test_single_param(
    target: str, input_value, expected_value, expected_from_fmeobjects
):
    """
    Test setting and getting single parameters via TransformerParameterParser and fmeobjects.FMETransformer.

    Values from both don't always agree, as TransformerParameterParser
    detects sentinel values and skips calling FMETransformer for them.
    However, depending on the parameter type, FMETransformer may not return sentinel values as-is.
    """
    transformer_name, version, param_name = target.split()
    parser = TransformerParameterParser(transformer_name, version=int(version))

    # One-off case: test attr is a conditional parameter that needs to be enabled.
    if transformer_name == "ExpressionEvaluator" and param_name == "NULL_ATTR_VALUE":
        parser["NULL_ATTR_MODE"] = "OTHER_NULL_VALUE_2"
        assert parser[param_name] == 0  # default value after enabling

    if input_value is not MISSING:
        assert parser.set(param_name, input_value)

    if expected_value is SAME:
        expected_value = input_value
    if inspect.isclass(expected_value) and issubclass(expected_value, Exception):
        with pytest.raises(expected_value):
            return parser[param_name]
    else:
        assert parser[param_name] == expected_value
        if isinstance(expected_value, ParameterState):
            # Ensure expected enum is actually an enum instance, not just the string.
            # Only applies to TransformerParameterParser's return value.
            assert isinstance(parser[param_name], Enum)

    if expected_from_fmeobjects is SAME:
        expected_from_fmeobjects = expected_value
    if inspect.isclass(expected_from_fmeobjects) and issubclass(
        expected_from_fmeobjects, Exception
    ):
        with pytest.raises(expected_from_fmeobjects):
            return parser.xformer.getParsedParamValue(param_name)
    else:
        assert (
            parser.xformer.getParsedParamValue(param_name) == expected_from_fmeobjects
        )
    return None


@pytest.fixture
def creator():
    return TransformerParameterParser("Creator", version=6)


def test_system_transformer(creator):
    t = creator
    assert t.is_required("NUM")
    assert not t.is_required("COORDSYS")  # Enabled but optional

    # Invalid type for name
    with pytest.raises(TypeError) as e:
        t.set(1, 1)  # noqa
    assert "must be str, failed to get string value" in str(e.value)

    # This doesn't clear default values
    assert t.set_all({})
    assert t["NUM"] == 1

    # TODO: Add test for conditionally hidden fields, which are possible in FMXJ


def check_disabled_param_access(xformer, param_name):
    if BUILD_NUM >= 25759:  # FMEFORM-34668 (see comments)
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
