"""
Tests for `fmeobjects.FMETransformer`.
"""

import re
import subprocess
from pathlib import Path

import fmeobjects
import pytest


# Allow this test to skip gracefully with pytestmark, if import fails.
FMETRANSFORMER_NOT_AVAILABLE = True
try:
    from fmeobjects import FMETransformer  # noqa

    FMETRANSFORMER_NOT_AVAILABLE = False
except ModuleNotFoundError:
    pass


pytestmark = pytest.mark.skipif(
    FMETRANSFORMER_NOT_AVAILABLE, reason="fmeobjects.FMETransformer not available"
)


def parse_package_list_cli_output(text):
    """Rudimentary parser for the output of `fme package list`."""
    text = re.split(r"={10,}", text)[1:]
    entries = []
    for entry in text:
        props = {}
        for row in entry.strip().split("\n"):
            key, value = row.split(" : ", maxsplit=1)
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = value.strip("[]").split(", ")
            props[key.strip()] = value
        entries.append(props)
    return entries


# Ask FME for its installed packages and find an arbitrary one with a transformer.
fme_exe_path = Path(fmeobjects.FMESession().fmeHome()) / "fme.exe"
if not fme_exe_path.is_file():
    fme_exe_path = fme_exe_path.parent / "fme"
result = subprocess.run(
    [fme_exe_path.as_posix(), "package", "list"], capture_output=True
)
arbitrary_fpkg_transformer = None
skip_reason = ""
if result.returncode != 0:
    skip_reason = result.stderr.decode("utf-8")
else:
    installed_packages = parse_package_list_cli_output(result.stdout.decode("utf-8"))
    for entry in installed_packages:
        if entry["Transformers"]:
            arbitrary_fpkg_transformer = f"{entry['Name']}.{entry['Transformers'][0]}"
            break
    else:
        skip_reason = "No packaged transformers installed"


@pytest.mark.parametrize(
    "transformer_names",
    [
        pytest.param(("VertexCreator", "ExcelStyler"), id="shipped_fmx_then_fmxj"),
        pytest.param(("ExcelStyler", "VertexCreator"), id="shipped_fmxj_then_fmx"),
        pytest.param(
            (arbitrary_fpkg_transformer, "VertexCreator"),
            id="fpkg_then_shipped",
            marks=[
                pytest.mark.skipif(skip_reason != "", reason=skip_reason),
                pytest.mark.xfail(
                    (25000 <= fmeobjects.FME_BUILD_NUM < 25034)
                    or fmeobjects.FME_BUILD_NUM < 24596,
                    reason="FMEENGINE-82163",
                ),
                pytest.mark.xfail(
                    (25050 <= fmeobjects.FME_BUILD_NUM < 25620)
                    or (25700 <= fmeobjects.FME_BUILD_NUM < 25745),
                    reason="FOUNDATION-8463",
                ),
            ],
        ),
        pytest.param(
            ("VertexCreator", arbitrary_fpkg_transformer),
            id="shipped then FPKG",
            marks=pytest.mark.skipif(skip_reason != "", reason=skip_reason),
        ),
    ],
)
def test_load_order(transformer_names):
    """
    Ensure that shipped and packaged transformers can be loaded in any order.

    This involves global state in FMETransformer. Run each case in a separate process.
    """
    for name in transformer_names:
        parts = name.rsplit(".", maxsplit=1)
        if len(parts) == 2:
            fmeobjects.FMETransformer(name, parts[0])
        else:
            fmeobjects.FMETransformer(name)
