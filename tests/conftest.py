"""
Run `pytest --fme-home=[PATH_TO_FME]` to run the tests against a specific FME installation.
If not specified, the FME_HOME environment variable is used.
Test initialization sets up access to fmeobjects before any tests are run,
so it's not necessary for the Python environment to already be configured for FME.
"""

import json
import os
import sys
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--fme-home",
        action="store",
        default=os.environ.get("FME_HOME"),
        help="Path to FME installation. Can also be set via FME_HOME environment variable.",
    )


def pytest_configure(config):
    print(f"Python {sys.version}")
    fme_home_str = config.getoption("--fme-home")
    if not fme_home_str:
        print(
            "Warning: FME_HOME not set; assuming environment already configured for fmeobjects"
        )
        return

    fme_home = Path(fme_home_str)
    if not fme_home.is_dir():
        raise ValueError(f"Invalid FME_HOME: {fme_home}")

    # Add FME DLLs to the DLL search path
    if os.name == "nt":
        os.add_dll_directory(str(fme_home))
        os.environ["PATH"] = f"{fme_home};{os.environ['PATH']}"

    # Add FME Python modules to the Python path
    for pth in (
        fme_home / "python",
        fme_home / "python" / f"python{sys.version_info.major}{sys.version_info.minor}",
    ):
        if str(pth) not in sys.path:
            sys.path.append(str(pth))
    print("Using FME_HOME:", fme_home)
    import fmeobjects

    print(f"{fmeobjects.FME_PRODUCT_NAME} {fmeobjects.FME_BUILD_STRING}")


@pytest.fixture(scope="package")
def vcr_config():
    def scrub_response(response):
        # Case-sensitive list of noisy and irrelevant response headers to remove.
        filtered_headers = [
            "Connection",
            "Date",
            "Server",
        ]
        for header in filtered_headers:
            response["headers"].pop(header, None)

        # Crudely prettify JSON responses to make them easier to read and diff nicely.
        # YAML output doesn't like indents, and newlines get doubled up.
        content_type = response["headers"].get("content-type", [""])[0]
        if content_type and "json" in content_type:
            json_body = json.loads(response["body"]["string"].decode("utf8"))
            response["body"]["string"] = json.dumps(json_body, indent=0).encode("utf8")

        return response

    return {
        "decode_compressed_response": True,
        "before_record_response": scrub_response,
    }
