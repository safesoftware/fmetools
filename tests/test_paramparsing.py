import fmeobjects
import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, example, given, settings

from fmetools.features import build_feature

# Allow this test to skip gracefully with pytestmark, if import fails.
try:
    from fmetools.paramparsing import TransformerParameters
except ModuleNotFoundError:
    pass


pytestmark = pytest.mark.skipif(
    fmeobjects.FME_BUILD_NUM < 23224, reason="Requires FME >= b23224"
)


@pytest.fixture
def creator():
    return TransformerParameters("Creator")


def test_system_transformer(creator):
    t = creator
    # Get params with defaults from transformer def
    assert t.get("NUM") == 1  # INTEGER type gives int
    assert t.get("CRE_ATTR") == "_creation_instance"
    assert t.is_required("NUM")
    assert not t.is_required("COORDSYS")
    # Set and get a param
    t.set("COORDSYS", "LL84")
    assert t.get("COORDSYS") == "LL84"
    # Set and get a param that doesn't exist
    t.set("foo", "bar")
    with pytest.raises(KeyError):
        t.get("foo")

    # Invalid type for name
    with pytest.raises(TypeError):
        t.set(1, 1)

    # This doesn't clear default values
    assert t.set_all({})
    assert t.get("NUM") == 1

    # Value not parsable as int
    assert t.set("NUM", "not an int")
    with pytest.raises(ValueError):
        assert t.get("NUM")

    # Test dependent parameters behaviour:
    # GEOMTYPE is ACTIVECHOICE involving GEOM and COORDS.
    # Check default values, then change GEOMTYPE and see its
    # dependent parameters get enabled/disabled with values.
    assert t.get("GEOMTYPE") == "Geometry Object"
    assert t.get("GEOM").startswith("<?xml")  # FME-decoded too
    assert not t.get("COORDS")  # Exists but disabled so no KeyError
    t.set("GEOMTYPE", "2D Coordinate List")
    assert not t.get("GEOM")  # Now disabled
    t.set("GEOMTYPE", "invalid")
    assert t.get("GEOMTYPE") == "invalid"  # Allowed
    assert t.get("GEOM")  # Enabled again


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
    assert creator.get("NUM") == 5  # Deserialized to int


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
        creator.get("foo")


@given(name=st.text(), pkg=st.one_of(st.text(), st.none()))
@settings(deadline=3000)
def test_transformer_not_found(name, pkg):
    with pytest.raises(ValueError):
        TransformerParameters(name, pkg)


@given(version=st.integers())
@example(0)
@example(1)  # Not defined for Creator
@example(2)  # Oldest definition in Creator.fmx
@example(3)  # Before COORDSYS was added
@settings(deadline=3000)
def test_versions(version):
    # All versions are silently accepted, even invalid ones.
    t = TransformerParameters("Creator", version=version)

    # Creator has no v1
    assert t.get("NUM") == 1  # Added in v2
    # COORDSYS added in v4, but it's accepted for any version
    assert t.set("COORDSYS", "LL84")
    assert t.get("COORDSYS") == "LL84"

    # Set a param that doesn't exist, and get it
    t.set("foo", "bar")
    with pytest.raises(KeyError):
        t.get("foo")

    t.change_version(version + 1)  # coverage
    assert t.get("NUM") == 1
