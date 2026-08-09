import base64
import os
import sqlite3
import pytest

# Core Data epoch offset: seconds between 2001-01-01 and 1970-01-01 UTC.
CD_EPOCH = 978307200

# A minimal real JPEG (2x2 pixel, produced via `sips`), base64-encoded so it
# can live inline as test fixture data. Starts with FF D8 FF.
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAASABIAAD/4QCARXhpZgAATU0AKgAAAAgABAEaAAUAAAABAAAAPgEb"
    "AAUAAAABAAAARgEoAAMAAAABAAIAAIdpAAQAAAABAAAATgAAAAAAAABIAAAAAQAAAEgAAAAB"
    "AAOgAQADAAAAAQABAACgAgAEAAAAAQAAAAKgAwAEAAAAAQAAAAIAAAAA/+0AOFBob3Rvc2hv"
    "cCAzLjAAOEJJTQQEAAAAAAAAOEJJTQQlAAAAAAAQ1B2M2Y8AsgTpgAmY7PhCfv/AABEIAAIA"
    "AgMBIgACEQEDEQH/xAAfAAABBQEBAQEBAQAAAAAAAAAAAQIDBAUGBwgJCgv/xAC1EAACAQMD"
    "AgQDBQUEBAAAAX0BAgMABBEFEiExQQYTUWEHInEUMoGRoQgjQrHBFVLR8CQzYnKCCQoWFxgZ"
    "GiUmJygpKjQ1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoOEhYaHiImK"
    "kpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4eLj5OXm5+jp"
    "6vHy8/T19vf4+fr/xAAfAQADAQEBAQEBAQEBAAAAAAAAAQIDBAUGBwgJCgv/xAC1EQACAQIE"
    "BAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEKFiQ04SXx"
    "FxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SFhoeI"
    "iYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo"
    "6ery8/T19vf4+fr/2wBDAAICAgICAgMCAgMFAwMDBQYFBQUFBggGBgYGBggKCAgICAgICgoK"
    "CgoKCgoMDAwMDAwODg4ODg8PDw8PDw8PDw//2wBDAQICAgQEBAcEBAcQCwkLEBAQEBAQEBAQ"
    "EBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/3QAEAAH/2gAMAwEAAhED"
    "EQA/APxuvYINSvJ9R1GNbq7upGlmmlAeSSRzuZ3ZslmYkkknJPJqt/Zemf8APpD/AN+1/wAK"
    "vUV/Vh/NZ//Z"
)
TINY_JPEG = base64.b64decode(TINY_JPEG_B64)

@pytest.fixture
def mela_db(tmp_path, monkeypatch):
    """Build a tiny SQLite store mimicking Mela's Core Data schema."""
    db_path = tmp_path / "Curcuma.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE ZRECIPEOBJECT (
            Z_PK INTEGER PRIMARY KEY, ZID VARCHAR,
            ZTITLE VARCHAR, ZINGREDIENTS VARCHAR, ZINSTRUCTIONS VARCHAR,
            ZNOTES VARCHAR, ZTEXT VARCHAR, ZNUTRITION VARCHAR, ZLINK VARCHAR,
            ZPREPTIME VARCHAR, ZCOOKTIME VARCHAR, ZTOTALTIME VARCHAR, ZYIELD VARCHAR,
            ZFAVORITE INTEGER, ZWANTTOCOOK INTEGER, ZDATE TIMESTAMP
        );
        CREATE TABLE ZRECIPETAG (Z_PK INTEGER PRIMARY KEY, ZTITLE VARCHAR);
        CREATE TABLE Z_4TAGS (Z_4RECIPES INTEGER, Z_5TAGS INTEGER);
        CREATE TABLE ZRECIPEIMAGEOBJECT (
            Z_PK INTEGER PRIMARY KEY, ZINDEX INTEGER, ZRECIPE INTEGER,
            ZHEIGHT INTEGER, ZWIDTH INTEGER, ZDATA BLOB
        );
        """
    )
    conn.executemany(
        "INSERT INTO ZRECIPEOBJECT (Z_PK, ZID, ZTITLE, ZINGREDIENTS, ZINSTRUCTIONS, "
        "ZNOTES, ZTEXT, ZNUTRITION, ZLINK, ZPREPTIME, ZCOOKTIME, ZTOTALTIME, ZYIELD, "
        "ZFAVORITE, ZWANTTOCOOK, ZDATE) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "u1", "Lemon Chicken", "chicken, lemon, garlic", "Roast it.",
             "family favorite", "Mains", "", "", "10 min", "40 min", "50 min", "4",
             1, 0, 700000000.0),
            (2, "u2", "Kale Soup", "kale, potato, sausage", "Simmer it.",
             "", "Soups", "", "http://x", "15 min", "30 min", "45 min", "6",
             0, 1, 700100000.0),
            (3, "u3", "Chocolate Cake", "flour, cocoa, sugar", "Bake it.",
             "", "Desserts", "", "", "20 min", "35 min", "55 min", "8",
             0, 0, 700200000.0),
        ],
    )
    conn.executemany("INSERT INTO ZRECIPETAG (Z_PK, ZTITLE) VALUES (?,?)",
                     [(10, "Dinner"), (11, "Comfort")])
    conn.executemany("INSERT INTO Z_4TAGS (Z_4RECIPES, Z_5TAGS) VALUES (?,?)",
                     [(1, 10), (2, 10), (2, 11)])

    # Recipe 1: one INLINE image (0x01 prefix + raw JPEG bytes).
    inline_blob = b"\x01" + TINY_JPEG

    # Recipe 2: one EXTERNAL image (0x02 prefix + 36-char uuid + NUL),
    # whose bytes live in .Curcuma_SUPPORT/_EXTERNAL_DATA next to the db.
    ext_uuid = "D2589AFC-F99E-4CDD-9E12-641A451BF233"
    ext_blob = b"\x02" + ext_uuid.encode("ascii") + b"\x00"
    ext_dir = tmp_path / ".Curcuma_SUPPORT" / "_EXTERNAL_DATA"
    ext_dir.mkdir(parents=True)
    (ext_dir / ext_uuid).write_bytes(TINY_JPEG)

    # Recipe 3 gets no image row.
    conn.executemany(
        "INSERT INTO ZRECIPEIMAGEOBJECT (Z_PK, ZINDEX, ZRECIPE, ZHEIGHT, ZWIDTH, ZDATA) "
        "VALUES (?,?,?,?,?,?)",
        [
            (1, 0, 1, 2, 2, inline_blob),
            (2, 0, 2, 2, 2, ext_blob),
        ],
    )

    conn.commit()
    conn.close()
    monkeypatch.setenv("MELA_DB_PATH", str(db_path))
    return str(db_path)
