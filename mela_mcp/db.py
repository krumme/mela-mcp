import os
import re
import sqlite3

_UUID_RE = re.compile(r"^[0-9A-Fa-f-]{36}$")

MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB

DEFAULT_DB_PATH = (
    "~/Library/Group Containers/66JC38RDUD.recipes.mela/Data/Curcuma.sqlite"
)

def get_db_path() -> str:
    override = os.environ.get("MELA_DB_PATH")
    path = override if override else os.path.expanduser(DEFAULT_DB_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Mela database not found at '{path}'. Set MELA_DB_PATH to override, "
            "or make sure the Mela app is installed and has synced recipes."
        )
    return path

def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or get_db_path()
    conn = None
    for params in ("mode=ro", "immutable=1"):
        try:
            conn = sqlite3.connect(f"file:{path}?{params}", uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("SELECT 1")
            return conn
        except sqlite3.DatabaseError:
            if conn is not None:
                conn.close()
                conn = None
            continue
    raise sqlite3.OperationalError(f"Could not open Mela database read-only: {path}")

def list_tags(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.ZTITLE AS tag, COUNT(j.Z_4RECIPES) AS count
        FROM ZRECIPETAG t
        LEFT JOIN Z_4TAGS j ON j.Z_5TAGS = t.Z_PK
        WHERE t.ZTITLE IS NOT NULL AND t.ZTITLE != ''
        GROUP BY t.Z_PK
        ORDER BY count DESC, tag ASC
        """
    ).fetchall()
    return [{"tag": r["tag"], "count": r["count"]} for r in rows]

from datetime import datetime, timezone

_CD_EPOCH = 978307200  # seconds between 1970-01-01 and 2001-01-01 UTC

def _coredata_ts_to_iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts + _CD_EPOCH, tz=timezone.utc).isoformat()

def _tags_for(conn: sqlite3.Connection, pk: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT t.ZTITLE AS tag FROM ZRECIPETAG t
        JOIN Z_4TAGS j ON j.Z_5TAGS = t.Z_PK
        WHERE j.Z_4RECIPES = ? AND t.ZTITLE IS NOT NULL AND t.ZTITLE != ''
        ORDER BY t.ZTITLE ASC
        """,
        (pk,),
    ).fetchall()
    return [r["tag"] for r in rows]

def get_recipe(conn: sqlite3.Connection, pk: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM ZRECIPEOBJECT WHERE Z_PK = ?", (pk,)
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["Z_PK"],
        "uuid": row["ZID"],
        "title": row["ZTITLE"],
        "ingredients": row["ZINGREDIENTS"],
        "instructions": row["ZINSTRUCTIONS"],
        "notes": row["ZNOTES"],
        "description": row["ZTEXT"],
        "nutrition": row["ZNUTRITION"],
        "link": row["ZLINK"],
        "prep_time": row["ZPREPTIME"],
        "cook_time": row["ZCOOKTIME"],
        "total_time": row["ZTOTALTIME"],
        "yield": row["ZYIELD"],
        "favorite": bool(row["ZFAVORITE"]),
        "want_to_cook": bool(row["ZWANTTOCOOK"]),
        "date_added": _coredata_ts_to_iso(row["ZDATE"]),
        "tags": _tags_for(conn, pk),
        "image_count": image_count(conn, pk),
    }

def image_count(conn: sqlite3.Connection, pk: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM ZRECIPEIMAGEOBJECT WHERE ZRECIPE = ?", (pk,)
    ).fetchone()
    return row["n"] if row else 0

def get_recipe_image_bytes(conn: sqlite3.Connection, db_path: str, pk: int,
                           index: int = 0) -> bytes | None:
    """Return raw (pre-conversion) image bytes for a recipe's image at `index`
    (0-based, ordered by ZINDEX), or None if unavailable."""
    if index < 0:
        return None
    rows = conn.execute(
        "SELECT ZDATA FROM ZRECIPEIMAGEOBJECT WHERE ZRECIPE = ? "
        "ORDER BY ZINDEX ASC, Z_PK ASC",
        (pk,),
    ).fetchall()
    if index >= len(rows):
        return None
    blob = rows[index]["ZDATA"]
    if not blob:
        return None
    prefix = blob[0]
    if prefix == 1:
        if len(blob) <= 1:
            return None
        return bytes(blob[1:])
    if prefix == 2:
        uuid = bytes(blob[1:37]).decode("ascii", "ignore")
        if not _UUID_RE.match(uuid):
            return None
        path = os.path.join(
            os.path.dirname(db_path), ".Curcuma_SUPPORT", "_EXTERNAL_DATA", uuid
        )
        try:
            if os.path.getsize(path) > MAX_IMAGE_BYTES:
                return None
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None
    return None

_SEARCH_COLS = (
    "ZTITLE", "ZINGREDIENTS", "ZINSTRUCTIONS",
    "ZNOTES", "ZTEXT", "ZNUTRITION", "ZLINK",
)

def _snippet(text: str, term: str, width: int = 120) -> str:
    lo = text.lower().find(term.lower())
    if lo < 0:
        return text[:width].strip()
    start = max(0, lo - width // 2)
    end = min(len(text), start + width)
    piece = text[start:end].strip()
    return ("…" if start > 0 else "") + piece + ("…" if end < len(text) else "")

def search_recipes(conn, query, tag=None, favorite=None,
                   want_to_cook=None, limit=20):
    terms = query.split()
    where, params = [], []
    for term in terms:
        ors = " OR ".join(f"r.{c} LIKE ? ESCAPE '\\'" for c in _SEARCH_COLS)
        where.append(f"({ors})")
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params.extend([like] * len(_SEARCH_COLS))
    if favorite is not None:
        where.append("r.ZFAVORITE = ?")
        params.append(1 if favorite else 0)
    if want_to_cook is not None:
        where.append("r.ZWANTTOCOOK = ?")
        params.append(1 if want_to_cook else 0)
    if tag:
        where.append(
            "EXISTS (SELECT 1 FROM Z_4TAGS j JOIN ZRECIPETAG t "
            "ON t.Z_PK = j.Z_5TAGS WHERE j.Z_4RECIPES = r.Z_PK AND t.ZTITLE = ?)"
        )
        params.append(tag)
    clause = " AND ".join(where) if where else "1"
    params.append(limit)
    rows = conn.execute(
        f"SELECT r.Z_PK AS id, r.ZTITLE AS title FROM ZRECIPEOBJECT r "
        f"WHERE {clause} ORDER BY r.ZTITLE ASC LIMIT ?",
        params,
    ).fetchall()
    results = []
    for row in rows:
        full = conn.execute(
            "SELECT " + ", ".join(_SEARCH_COLS)
            + " FROM ZRECIPEOBJECT WHERE Z_PK = ?",
            (row["id"],),
        ).fetchone()
        blob = " ".join(str(full[c] or "") for c in _SEARCH_COLS)
        snip = _snippet(blob, terms[0]) if terms else blob[:120]
        results.append({
            "id": row["id"], "title": row["title"],
            "tags": _tags_for(conn, row["id"]), "snippet": snip,
        })
    return results
