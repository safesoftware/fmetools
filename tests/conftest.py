# Import these modules just for parsing coverage.
# Remove when these modules get imported elsewhere for tests.
from fmetools import localize, scripted_selection, webservices  # noqa F401

import json

import pytest


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
