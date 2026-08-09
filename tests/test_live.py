import os
import shutil
import pytest
from mela_mcp import db, imaging

# The live tests read the REAL Mela library, which triggers a macOS privacy
# prompt ("python would like to access data from other apps"). They are opt-in
# so routine `pytest` never touches the real store: run with MELA_LIVE_TEST=1.
pytestmark = pytest.mark.skipif(
    not os.environ.get("MELA_LIVE_TEST"),
    reason="Live Mela tests are opt-in; set MELA_LIVE_TEST=1 to run them.",
)

def _real_db_present(monkeypatch):
    monkeypatch.delenv("MELA_DB_PATH", raising=False)
    try:
        return db.get_db_path()
    except FileNotFoundError:
        return None

def test_live_search_and_get(monkeypatch):
    if _real_db_present(monkeypatch) is None:
        pytest.skip("Real Mela store not present on this machine.")
    conn = db.connect()
    assert db.list_tags(conn)  # non-empty on a real library
    hits = db.search_recipes(conn, "a", limit=5)  # 'a' matches almost anything
    assert hits, "expected at least one recipe"
    full = db.get_recipe(conn, hits[0]["id"])
    assert full["title"]

def test_live_recipe_image_converts_to_jpeg(monkeypatch):
    if _real_db_present(monkeypatch) is None:
        pytest.skip("Real Mela store not present on this machine.")
    if shutil.which("sips") is None:
        pytest.skip("sips not available on this platform.")
    db_path = db.get_db_path()
    conn = db.connect()
    hits = conn.execute(
        "SELECT DISTINCT ZRECIPE FROM ZRECIPEIMAGEOBJECT LIMIT 20"
    ).fetchall()
    for row in hits:
        raw = db.get_recipe_image_bytes(conn, db_path, row["ZRECIPE"], 0)
        if raw is None:
            continue
        jpeg = imaging.to_jpeg(raw)
        assert jpeg is not None
        assert jpeg[:3] == b"\xff\xd8\xff"
        return
    pytest.skip("No recipe with a recoverable image found in real library.")
