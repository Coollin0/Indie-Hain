# data/store.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Dict, List, Optional, Set
from dataclasses import dataclass
import json

from services.env import session_path

SESSION_JSON_PATH = session_path()

# --- Auth: Session & Rollen (failsafe Import) ---
try:
    from auth_service import User, AuthService  # type: ignore
except Exception:
    User = None        # type: ignore
    AuthService = None # type: ignore

auth_service = AuthService() if AuthService else None


@dataclass
class SessionState:
    current_user: Optional["User"] = None  # type: ignore


session = SessionState()

def is_logged_in() -> bool:
    return session.current_user is not None

def has_role(*roles: str) -> bool:
    return is_logged_in() and getattr(session.current_user, "role", None) in roles

def _current_user_id() -> Optional[int]:
    return getattr(session.current_user, "id", None) if is_logged_in() else None


# --- DB ---
DB_PATH = (Path(__file__).resolve().parent / "indiehain.db")

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# === Schemas (mit cover_url + description) ================================

LIB_SCHEMA_V2 = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS library (
    slug        TEXT    NOT NULL DEFAULT '',
    user_id      INTEGER NOT NULL,
    game_id      INTEGER NOT NULL,
    title        TEXT    NOT NULL,
    price        REAL    NOT NULL,
    cover_url    TEXT    NOT NULL DEFAULT '',
    description  TEXT    NOT NULL DEFAULT '',
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_library_user ON library(user_id);
"""

LIB_SCHEMA_V1 = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS library (
    game_id      INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    price        REAL NOT NULL,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CART_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cart (
    slug       TEXT    NOT NULL DEFAULT '',
    user_id    INTEGER NOT NULL,
    game_id    INTEGER NOT NULL,
    title      TEXT NOT NULL,
    price      REAL  NOT NULL,
    cover_url  TEXT    NOT NULL DEFAULT '',
    description TEXT   NOT NULL DEFAULT '',
    added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id);
"""



# === Schema-Helpers =======================================================

def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None

def _columns(cur, table: str) -> Set[str]:
    cur.execute(f"PRAGMA table_info({table});")
    return {row[1] for row in cur.fetchall()}

def _library_has_user_id(cur) -> bool:
    if not _table_exists(cur, "library"):
        return False
    return "user_id" in _columns(cur, "library")


# === Cart-Schema prüfen/migrieren (idempotent) ============================

def ensure_cart_schema():
    with _conn() as con:
        cur = con.cursor()
        if not _table_exists(cur, "cart"):
            cur.executescript(CART_SCHEMA)
            con.commit()
            return

        cols = _columns(cur, "cart")
        if "title" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "price" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN price REAL NOT NULL DEFAULT 0.0")
        if "cover_url" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN cover_url TEXT NOT NULL DEFAULT ''")
        if "description" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "added_at" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if "slug" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN slug TEXT NOT NULL DEFAULT ''")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id)")
        con.commit()

# === Library-Schema prüfen/migrieren (idempotent) =========================

def ensure_library_schema(owner_user_id: Optional[int] = None):
    with _conn() as con:
        cur = con.cursor()

        if not _table_exists(cur, "library"):
            cur.executescript(LIB_SCHEMA_V2)
            con.commit()
            return

        cols = _columns(cur, "library")

        # Alt ohne user_id → migrieren auf V2
        if "user_id" not in cols and owner_user_id is not None:
            con.execute("ALTER TABLE library RENAME TO library_old;")
            con.executescript(LIB_SCHEMA_V2)
            # alte Tabelle hat keine cover_url/description → mit '' vorbelegen
            con.execute("""
                INSERT INTO library (user_id, game_id, title, price, cover_url, description, purchased_at)
                SELECT ?, game_id, title, price, '' AS cover_url, '' AS description, purchased_at
                FROM library_old;
            """, (int(owner_user_id),))
            con.execute("DROP TABLE library_old;")
            con.commit()
            return

        # Spalten ggf. nachrüsten
        if "slug" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN slug TEXT NOT NULL DEFAULT ''")
        if "title" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "price" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN price REAL NOT NULL DEFAULT 0.0")
        if "cover_url" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN cover_url TEXT NOT NULL DEFAULT ''")
        if "description" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "purchased_at" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_library_user ON library(user_id)")
        con.commit()


# === Init & Migration =====================================================

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        cur = con.cursor()
        cur.executescript(CART_SCHEMA)
        if not _table_exists(cur, "library"):
            cur.executescript(LIB_SCHEMA_V2)
        con.commit()
    ensure_cart_schema()
    ensure_library_schema()

def ensure_user_scoped_library(owner_user_id: int):
    with _conn() as con:
        cur = con.cursor()
        if not _table_exists(cur, "library"):
            cur.executescript(LIB_SCHEMA_V2)
            con.commit()
            return

        if _library_has_user_id(cur):
            return

        con.execute("ALTER TABLE library RENAME TO library_old;")
        con.executescript(LIB_SCHEMA_V2)
        con.execute("""
            INSERT INTO library (user_id, game_id, title, price, cover_url, description, purchased_at)
            SELECT ?, game_id, title, price, '' AS cover_url, '' AS description, purchased_at
            FROM library_old;
        """, (int(owner_user_id),))
        con.execute("DROP TABLE library_old;")
        con.commit()


# === Library (user-spezifisch) ============================================

def get_library_ids() -> Set[int]:
    uid = _current_user_id()
    if uid is None:
        return set()
    ensure_library_schema()
    with _conn() as con:
        cur = con.cursor()
        if not _library_has_user_id(cur):
            return set()
        cur.execute("SELECT game_id FROM library WHERE user_id=?;", (int(uid),))
        return {int(r[0]) for r in cur.fetchall()}

def get_library_items() -> List[Dict]:
    uid = _current_user_id()
    if uid is None:
        return []
    ensure_library_schema()
    with _conn() as con:
        cur = con.cursor()
        if not _library_has_user_id(cur):
            return []
        cur.execute("""
            SELECT game_id, slug, title, price, cover_url, description, purchased_at
            FROM library
            WHERE user_id=?
            ORDER BY purchased_at DESC;
        """, (int(uid),))
        out: List[Dict] = []
        for row in cur.fetchall():
            out.append({
                "id": int(row[0]),
                "slug": row[1] or "",
                "title": row[2] or "",
                "price": float(row[3] or 0.0),
                "cover_url": row[4] or "",
                "description": row[5] or "",
                "purchased_at": row[6],
            })
        return out

def add_to_library(game: Dict):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_library_schema(uid)
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO library (user_id, game_id, slug, title, price, cover_url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            int(uid),
            int(game["id"]),
            game.get("slug") or "",
            game.get("title") or "",
            float(game.get("price") or 0.0),
            game.get("cover_url") or "",
            game.get("description") or "",
        ))
        con.commit()

def add_many_to_library(games: Iterable[Dict]):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_library_schema(uid)
    rows = [(
        int(uid),
        int(g.get("id", 0)),
        g.get("slug") or "",
        g.get("title") or "",
        float(g.get("price") or 0.0),
        g.get("cover_url") or "",
        g.get("description") or "",
    ) for g in games]
    if not rows:
        return
    with _conn() as con:
        cur = con.cursor()
        cur.executemany("""
            INSERT OR REPLACE INTO library (user_id, game_id, slug, title, price, cover_url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, rows)
        con.commit()

def remove_from_library(game_id: int):
    uid = _current_user_id()
    if uid is None:
        return
    ensure_library_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM library WHERE user_id=? AND game_id=?;", (int(uid), int(game_id)))
        con.commit()


# === Cart (user-spezifisch) ===============================================

def cart_get_items() -> List[Dict]:
    uid = _current_user_id()
    if uid is None:
        return []
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT game_id, slug, title, price, cover_url, description, added_at
            FROM cart
            WHERE user_id=?
            ORDER BY added_at DESC;
        """, (int(uid),))
        out: List[Dict] = []
        for row in cur.fetchall():
            out.append({
                "id": int(row[0]),
                "slug": row[1] or "",
                "title": row[2] or "",
                "price": float(row[3] or 0.0),
                "cover_url": row[4] or "",
                "description": row[5] or "",
                "added_at": row[6],
            })
        return out

def cart_get_ids() -> Set[int]:
    return {int(x["id"]) for x in cart_get_items()}

def cart_add(game: Dict):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        # ON CONFLICT: aktualisiert Metadaten, falls der Titel schon im Cart liegt
        cur.execute("""
            INSERT INTO cart (user_id, game_id, slug, title, price, cover_url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, game_id) DO UPDATE SET
              slug=excluded.slug,
              title=excluded.title,
              price=excluded.price,
              cover_url=excluded.cover_url,
              description=excluded.description
        """, (
            int(uid),
            int(game.get("id", 0)),
            game.get("slug") or "",
            game.get("title") or "",
            float(game.get("price") or 0.0),
            game.get("cover_url") or "",
            game.get("description") or "",
        ))
        con.commit()

def cart_add_many(games: Iterable[Dict]):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_cart_schema()
    rows = [(
        int(uid),
        int(g.get("id", 0)),
        g.get("slug") or "",
        g.get("title") or "",
        float(g.get("price") or 0.0),
        g.get("cover_url") or "",
        g.get("description") or "",
    ) for g in games]
    if not rows:
        return
    with _conn() as con:
        cur = con.cursor()
        cur.executemany("""
            INSERT INTO cart (user_id, game_id, slug, title, price, cover_url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, game_id) DO UPDATE SET
              slug=excluded.slug,
              title=excluded.title,
              price=excluded.price,
              cover_url=excluded.cover_url,
              description=excluded.description
        """, rows)
        con.commit()

def cart_remove(game_id: int):
    uid = _current_user_id()
    if uid is None:
        return
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM cart WHERE user_id=? AND game_id=?", (int(uid), int(game_id)))
        con.commit()

def cart_clear():
    uid = _current_user_id()
    if uid is None:
        return
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM cart WHERE user_id=?", (int(uid),))
        con.commit()

def cart_replace_all(games: Iterable[Dict]):
    uid = _current_user_id()
    if uid is None:
        return
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM cart WHERE user_id=?", (int(uid),))
        rows = [(
            int(uid),
            int(g.get("id", 0)),
            g.get("slug") or "",
            g.get("title") or "",
            float(g.get("price") or 0.0),
            g.get("cover_url") or "",
            g.get("description") or "",
        ) for g in games]
        if rows:
            cur.executemany("""
                INSERT INTO cart (user_id, game_id, slug, title, price, cover_url, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, game_id) DO UPDATE SET
                  slug=excluded.slug,
                  title=excluded.title,
                  price=excluded.price,
                  cover_url=excluded.cover_url,
                  description=excluded.description
            """, rows)
        con.commit()


# === Session-Persistenz ====================================================

SESSION_PATH = session_path()

def save_session(user=None):
    """
    Persistiert die aktuelle Session (GUI) und spiegelt sie für den Uploader.
    Falls kein user übergeben wird, wird session.current_user genutzt.
    """
    # existierende Persistierung unverändert lassen:
    if is_logged_in() and getattr(session.current_user, "id", None) is not None and auth_service:
        payload = {
            "user_id": int(session.current_user.id),
            **auth_service.session_payload(),
        }
        SESSION_PATH.write_text(json.dumps(payload))
    else:
        clear_session()
        return

    if user is None:
        user = session.current_user

    # --- Spiegelung für den Uploader (robust für dict/objekt) ---
    # Sitzung für Hintergrundprozesse spiegeln
    # Session-Datei ist bereits geschrieben; keine doppelte Persistierung.

def safe_session(user):
    return save_session(user)

def sync_uploader_session_from_current():
    save_session()

def clear_session():
    try:
        SESSION_PATH.unlink()
    except FileNotFoundError:
        pass
    try:
        SESSION_JSON_PATH.unlink(missing_ok=True)
    except Exception:
        pass

def load_session() -> bool:
    if not SESSION_PATH.exists() or not auth_service:
        return False
    try:
        data = json.loads(SESSION_PATH.read_text())
        refresh_token = data.get("refresh_token")
        device_id = data.get("device_id")
        auth_service.set_session(refresh_token, device_id)
        u = auth_service.me()
        if u:
            session.current_user = u
            return True
    except Exception:
        pass
    clear_session()
    return False


def auth_headers() -> dict:
    if not auth_service:
        return {}
    token = auth_service.access_token()
    if not token and auth_service.session_payload().get("refresh_token"):
        user = auth_service.refresh()
        if user:
            session.current_user = user
            save_session()
            token = auth_service.access_token()
        else:
            session.current_user = None
            clear_session()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
