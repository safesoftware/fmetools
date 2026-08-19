from collections import Counter

from hypothesis import assume, example, given
from hypothesis.strategies import integers, lists, text

from fmetools.utils import stringarray_to_dict


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
