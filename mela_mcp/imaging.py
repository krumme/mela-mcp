"""Convert arbitrary recipe image bytes (JPEG/HEIC/WebP/PNG) to a downscaled
JPEG using the macOS `sips` CLI."""

import os
import subprocess
import tempfile


def to_jpeg(raw: bytes, max_edge: int = 512) -> bytes | None:
    """Convert `raw` image bytes to a downscaled JPEG. Returns None on any
    failure; never raises."""
    in_fd, in_path = tempfile.mkstemp(suffix=".img")
    out_fd, out_path = tempfile.mkstemp(suffix=".jpg")
    os.close(out_fd)
    try:
        with os.fdopen(in_fd, "wb") as f:
            f.write(raw)
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", str(max_edge), in_path,
             "--out", out_path],
            capture_output=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None
        if os.path.getsize(out_path) == 0:
            return None
        with open(out_path, "rb") as f:
            return f.read()
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        for path in (in_path, out_path):
            try:
                os.remove(path)
            except OSError:
                pass
