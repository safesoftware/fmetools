import fmeobjects
import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from fmetools.features import build_feature

# Allow this test to skip gracefully with pytestmark, if import fails.
try:
    from fmetools.paramparsing import TransformerParameterParser
except ModuleNotFoundError:
    pass


pytestmark = pytest.mark.skipif(
    fmeobjects.FME_BUILD_NUM < 23224, reason="Requires FME >= b23224"
)


@pytest.fixture
def creator():
    return TransformerParameterParser("Creator")


def test_system_transformer(creator):
    t = creator
    # Get params with defaults from transformer def
    assert t["NUM"] == 1  # INTEGER type gives int
    assert t["CRE_ATTR"] == "_creation_instance"
    assert t.is_required("NUM")
    assert not t.is_required("COORDSYS")
    # Set and get a param
    t.set("COORDSYS", "LL84")
    assert t["COORDSYS"] == "LL84"
    # Set and get a param that doesn't exist
    t.set("foo", "bar")
    with pytest.raises(KeyError):
        t.get("foo", prefix=None)

    with pytest.raises(KeyError):
        t.get("NUM")  # ___XF_NUM doesn't exist

    # Invalid type for name
    with pytest.raises(TypeError):
        t.set(1, 1)

    # This doesn't clear default values
    assert t.set_all({})
    assert t["NUM"] == 1

    # Value not parsable as int
    assert t.set("NUM", "not an int")
    with pytest.raises(ValueError):
        assert t["NUM"]

    # Test dependent parameters behaviour:
    # GEOMTYPE is ACTIVECHOICE involving GEOM and COORDS.
    # Check default values, then change GEOMTYPE and see its
    # dependent parameters get enabled/disabled with values.
    assert t["GEOMTYPE"] == "Geometry Object"
    assert t["GEOM"].startswith("<?xml")  # FME-decoded too
    assert not t["COORDS"]  # Exists but disabled so no KeyError
    t.set("GEOMTYPE", "2D Coordinate List")
    assert not t["GEOM"]  # Now disabled
    t.set("GEOMTYPE", "invalid")
    assert t["GEOMTYPE"] == "invalid"  # Allowed
    assert t["GEOM"]  # Enabled again


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
