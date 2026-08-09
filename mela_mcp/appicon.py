"""Read the Mela app icon from the locally-installed app, if present.

We never bundle Mela's artwork in this repo. Instead, at runtime we look
for the icon inside the installed Mela.app and, if found, expose it as a
data: URI for MCP server-info icons. If Mela isn't installed, or the icon
can't be parsed for any reason, this degrades gracefully to None.
"""

import base64
import os

ICNS_PATH = "/Applications/Mela.app/Contents/Resources/AppIcon.icns"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Preference order: ic07 (128px), then ic13 (256px), then ic11 (32px).
PREFERRED_TYPES = (b"ic07", b"ic13", b"ic11")


def _extract_png_from_icns(data: bytes) -> bytes | None:
    """Parse an icns byte buffer and return the preferred PNG icon entry's
    body, or None if the buffer is malformed or has no usable PNG entry.
    Pure function of its input; never raises."""
    entries = {}
    if data[:4] != b"icns":
        return None
    total_length = int.from_bytes(data[4:8], "big")
    pos = 8
    end = min(total_length, len(data))
    while pos + 8 <= end:
        type_code = data[pos:pos + 4]
        entry_length = int.from_bytes(data[pos + 4:pos + 8], "big")
        if entry_length < 8:
            break
        body_start = pos + 8
        body_end = pos + entry_length
        if body_end > end:
            break
        body = data[body_start:body_end]
        if body.startswith(PNG_SIGNATURE):
            entries[type_code] = body
        pos += entry_length
    for type_code in PREFERRED_TYPES:
        body = entries.get(type_code)
        if body:
            return body
    return None


def mela_icon_data_uri() -> str | None:
    """Return a data: URI for the Mela app icon, or None if unavailable."""
    try:
        if not os.path.isfile(ICNS_PATH):
            return None
        with open(ICNS_PATH, "rb") as f:
            data = f.read()
        body = _extract_png_from_icns(data)
        if body is None:
            return None
        return "data:image/png;base64," + base64.b64encode(body).decode("ascii")
    except Exception:
        return None
