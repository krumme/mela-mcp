import asyncio
import base64
import os

import pytest

from mela_mcp import appicon, server

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# A known-good, minimal valid 1x1 PNG.
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _icns_with_ic07(body: bytes) -> bytes:
    entry_length = len(body) + 8
    entry = b"ic07" + entry_length.to_bytes(4, "big") + body
    total_length = 8 + len(entry)
    return b"icns" + total_length.to_bytes(4, "big") + entry


def test_mela_icon_data_uri():
    if not os.path.isfile(appicon.ICNS_PATH):
        pytest.skip("Mela not installed on this machine.")
    uri = appicon.mela_icon_data_uri()
    assert isinstance(uri, str), "Mela is installed on this machine; expected a data URI, got None"
    assert uri.startswith("data:image/png;base64,")
    encoded = uri[len("data:image/png;base64,"):]
    decoded = base64.b64decode(encoded)
    assert decoded.startswith(PNG_SIGNATURE)


def test_server_still_registers_tools():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"search_recipes", "get_recipe", "list_tags"} <= names


def test_extract_png_from_icns_empty():
    assert appicon._extract_png_from_icns(b"") is None


def test_extract_png_from_icns_magic_only():
    assert appicon._extract_png_from_icns(b"icns") is None


def test_extract_png_from_icns_header_only():
    assert appicon._extract_png_from_icns(b"icns\x00\x00\x00\x08") is None


def test_extract_png_from_icns_truncated_entry():
    # Entry header present, but its declared body bytes are missing.
    data = b"icns\x00\x00\x00\x20ic07\x00\x00\x00\x20"
    assert appicon._extract_png_from_icns(data) is None


def test_extract_png_from_icns_entry_length_too_small():
    # entry_length < 8 can't even fit the entry's own header.
    data = b"icns\x00\x00\x00\x14ic07\x00\x00\x00\x04" + TINY_PNG
    assert appicon._extract_png_from_icns(data) is None


def test_extract_png_from_icns_entry_length_exceeds_buffer():
    # entry_length claims far more bytes than actually remain in the buffer.
    data = b"icns\x00\x00\x00\x64ic07\x00\x00\x00\x64" + TINY_PNG
    assert appicon._extract_png_from_icns(data) is None


def test_extract_png_from_icns_valid_minimal():
    data = _icns_with_ic07(TINY_PNG)
    assert appicon._extract_png_from_icns(data) == TINY_PNG
