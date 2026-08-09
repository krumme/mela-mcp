import os
import shutil
import sqlite3

import pytest

from mela_mcp import db, imaging

sips_missing = shutil.which("sips") is None


def _insert_image_row(db_path, pk, zindex, recipe, blob):
    raw_conn = sqlite3.connect(db_path)
    raw_conn.execute(
        "INSERT INTO ZRECIPEIMAGEOBJECT (Z_PK, ZINDEX, ZRECIPE, ZHEIGHT, ZWIDTH, ZDATA) "
        "VALUES (?,?,?,1,1,?)",
        (pk, zindex, recipe, blob),
    )
    raw_conn.commit()
    raw_conn.close()


def test_image_count(mela_db):
    conn = db.connect()
    assert db.image_count(conn, 1) == 1
    assert db.image_count(conn, 2) == 1
    assert db.image_count(conn, 3) == 0


def test_get_recipe_image_bytes_inline(mela_db):
    conn = db.connect()
    raw = db.get_recipe_image_bytes(conn, db.get_db_path(), 1, 0)
    assert raw is not None
    assert raw[:3] == b"\xff\xd8\xff"


def test_get_recipe_image_bytes_external(mela_db):
    conn = db.connect()
    raw = db.get_recipe_image_bytes(conn, db.get_db_path(), 2, 0)
    assert raw is not None
    assert raw[:3] == b"\xff\xd8\xff"


def test_get_recipe_image_bytes_no_image(mela_db):
    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 3, 0) is None


def test_get_recipe_image_bytes_out_of_range_index(mela_db):
    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 1, 5) is None
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 1, -1) is None


def test_get_recipe_image_bytes_rejects_path_traversal(mela_db):
    import sqlite3

    raw_conn = sqlite3.connect(mela_db)
    raw_conn.row_factory = sqlite3.Row
    bad_uuid_payload = ("../" * 12).encode("ascii")[:36]
    raw_conn.execute(
        "INSERT INTO ZRECIPEIMAGEOBJECT (Z_PK, ZINDEX, ZRECIPE, ZHEIGHT, ZWIDTH, ZDATA) "
        "VALUES (99, 0, 3, 1, 1, ?)",
        (b"\x02" + bad_uuid_payload + b"\x00",),
    )
    raw_conn.commit()
    raw_conn.close()

    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 3, 0) is None


def test_get_recipe_image_bytes_unknown_prefix(mela_db):
    _insert_image_row(mela_db, 100, 0, 3, b"\x03someunknownformatbytes")
    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 3, 0) is None


def test_get_recipe_image_bytes_missing_external_file(mela_db):
    missing_uuid = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
    blob = b"\x02" + missing_uuid.encode("ascii") + b"\x00"
    _insert_image_row(mela_db, 101, 0, 3, blob)
    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 3, 0) is None


def test_get_recipe_image_bytes_oversized_external_file(mela_db, monkeypatch):
    big_uuid = "11111111-2222-3333-4444-555555555555"
    ext_dir = os.path.join(os.path.dirname(mela_db), ".Curcuma_SUPPORT", "_EXTERNAL_DATA")
    os.makedirs(ext_dir, exist_ok=True)
    big_path = os.path.join(ext_dir, big_uuid)
    with open(big_path, "wb") as f:
        f.write(b"\x00" * 1000)
    monkeypatch.setattr(db, "MAX_IMAGE_BYTES", 100)
    blob = b"\x02" + big_uuid.encode("ascii") + b"\x00"
    _insert_image_row(mela_db, 102, 0, 3, blob)
    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 3, 0) is None


def test_get_recipe_image_bytes_empty_inline(mela_db):
    _insert_image_row(mela_db, 103, 0, 3, b"\x01")
    conn = db.connect()
    assert db.get_recipe_image_bytes(conn, db.get_db_path(), 3, 0) is None


def test_get_recipe_includes_image_count(mela_db):
    conn = db.connect()
    r = db.get_recipe(conn, 1)
    assert r["image_count"] == 1
    r3 = db.get_recipe(conn, 3)
    assert r3["image_count"] == 0


@pytest.mark.skipif(sips_missing, reason="sips not available on this platform")
def test_to_jpeg(mela_db):
    conn = db.connect()
    raw = db.get_recipe_image_bytes(conn, db.get_db_path(), 1, 0)
    jpeg = imaging.to_jpeg(raw)
    assert jpeg is not None
    assert jpeg[:3] == b"\xff\xd8\xff"


