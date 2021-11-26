# coding: utf-8

from collections import Counter

from hypothesis import given, assume, example, settings
from hypothesis.strategies import integers, text, lists

from fmetools.parsers import stringarray_to_dict, parse_def_line


@given(lists(text(), max_size=6), integers(min_value=0, max_value=6))
@example(["list", "0", "list", "1"], 0)
def test_stringarray_to_dict(stringarray, start):
    assume((len(stringarray) - start) % 2 == 0)
    parsed = stringarray_to_dict(stringarray, start=start)
    keys = stringarray[start::2]
    if not keys:
        return
    top_key, count = Counter(keys).most_common(1)[0]
    if count > 1:
        assert isinstance(parsed[top_key], list)
    else:
        assert parsed[top_key] == stringarray[stringarray.index(top_key, start) + 1]


@given(lists(text(min_size=1), max_size=10), integers(0, 2))
@settings(deadline=None)
def test_parse_def_line(keys, num_matching_options):
    # Build a dummy DEF line with arbitrary key-values.
    line = ["foo"] * len(keys) * 2
    line[0::2] = keys
    line[1::2] = ["foo"] * len(keys)
    line[:0] = ["DEF_1", "feattype"]
    # Pick arbitrary key(s) to consider as options.
    # The remaining keys are considered user attributes.
    options = {"not_present"} | set(keys[:num_matching_options])
    parsed = parse_def_line(line, options)

    assert parsed.feature_type == "feattype"
    assert parsed.options["not_present"] is None  # the missing option
    assert not options & set(parsed.attributes.keys())  # options removed from attrs
    assert set(parsed.options.keys()) == options  # all requested options are returned

    # An ordered comparison of user attrs
    expected_user_attrs = [v for v in line[2::2] if v not in options]
    if expected_user_attrs:
        # Don't proceed if there are dupe user attrs.
        assume(Counter(expected_user_attrs).most_common()[0][1] == 1)
    assert list(parsed.attributes.keys()) == expected_user_attrs
