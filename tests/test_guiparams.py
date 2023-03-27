import re

import pytest
from fmeobjects import FMEFeature
from hypothesis import example, given, settings
from hypothesis import strategies as st

from fmetools.guiparams import (
    BoolParser,
    FloatParser,
    GuiParameterParser,
    GuiType,
    IntParser,
    ListParser,
    StringParser,
    parse_gui_type,
)


@pytest.mark.parametrize(
    "gui_type, parsed",
    [
        ("STRING", GuiType("STRING", False, False, None)),
        (
            "COLOR COLOR_SPEC%RGBAF%COLOR_VALUE_FORMAT%rgb()",
            GuiType("COLOR", False, False, "COLOR_SPEC%RGBAF%COLOR_VALUE_FORMAT%rgb()"),
        ),
        ("STRING_ENCODED_OR_ATTR", GuiType("STRING", True, True, None)),
    ],
)
def test_parse_gui_type(gui_type, parsed):
    assert parse_gui_type(gui_type) == parsed


@given(st.text())
@example("No")
def test_boolparser(value):
    parser = BoolParser()
    parsed = parser(value)
    assert parsed == parser(parsed)
    if not value or value == "No":
        assert not parsed
    assert isinstance(parsed, bool)


@given(st.text())
@example("10")
@example("10.1")
def test_intparser(value):
    parser = IntParser()
    if value == "":
        assert parser(value) is None
        return
    if not re.match(r"^\d+\s*$", value):
        with pytest.raises(ValueError):
            parser(value)
        return
    parsed = parser(value)
    assert parsed == parser(parsed)
    assert isinstance(parsed, int)


@given(st.text())
@example("10")
@example("10.1")
def test_floatparser(value):
    parser = FloatParser()
    if value == "":
        assert parser(value) is None
        return
    valid_float = True
    try:
        # float() can also parse "1E5", "1e0", etc.
        float(value)
    except ValueError:
        valid_float = False

    if valid_float:
        parsed = parser(value)
        assert parsed == parser(parsed)
        assert isinstance(parsed, float)
    else:
        with pytest.raises(ValueError):
            parser(value)


@given(value=st.text(), encoded=st.booleans())
@example("<space>", True)
@example("<space>", False)
@settings(deadline=None)
def test_stringparser(value, encoded):
    parser = StringParser(encoded=encoded)
    parsed = parser(value)
    if value == "<space>":
        assert parsed == " " if encoded else "<space>"
    assert isinstance(parsed, str)


@given(value=st.text())
@settings(deadline=None)
def test_listparser(value):
    parser = ListParser()
    parsed = parser(value)
    assert parsed == parser(parsed)
    assert isinstance(parsed, list)
    if value == "":
        assert parsed == []
    else:
        assert len(parsed) == len(value.split())


def test_parser():
    parser = GuiParameterParser({"ATTR1": "STRING_ENCODED", "ATTR2": "INTEGER"})
    feature = FMEFeature()
    feature.setAttribute("ATTR1", "hello<space>world")
    assert parser.get(feature, "ATTR1") == "hello world"
    assert parser.get(feature, "ATTR2") is None
    assert parser.get(feature, "ATTR2", default="10") == "10"
    with pytest.raises(KeyError):
        parser.get(feature, "not a parameter")
