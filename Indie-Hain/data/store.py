import sqlite3
from pathlib import Path
from typing import Iterable, Dict, List, Optional, Set
from dataclasses import dataclass
import json

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
    return sqlite3.connect(DB_PATH)

# --- Schemas ---
LIB_SCHEMA_V2 = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS library (
    user_id    INTEGER NOT NULL,
    game_id    INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    price      REAL    NOT NULL,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_library_user ON library(user_id);
"""
LIB_SCHEMA_V1 = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS library (
    game_id INTEGER PRIMARY KEY,
    title   TEXT NOT NULL,
    price   REAL NOT NULL,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
CART_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cart (
    user_id    INTEGER NOT NULL,
    game_id    INTEGER NOT NULL,
    title      TEXT NOT NULL,
    price      REAL  NOT NULL,
    added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id);
"""

def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None

def _library_has_user_id(cur) -> bool:
    if not _table_exists(cur, "library"):
        return False
    cur.execute("PRAGMA table_info(library);")
    cols = {row[1] for row in cur.fetchall()}
    return "user_id" in cols

# --- Cart-Schema prüfen/migrieren (idempotent) ---
def ensure_cart_schema():
    with _conn() as con:
        cur = con.cursor()
        if not _table_exists(cur, "cart"):
            cur.executescript(CART_SCHEMA)
            con.commit()
            return
        cur.execute("PRAGMA table_info(cart);")
        cols = {row[1] for row in cur.fetchall()}
        if "title" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "price" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN price REAL NOT NULL DEFAULT 0.0")
        if "added_at" not in cols:
            cur.execute("ALTER TABLE cart ADD COLUMN added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id)")
        con.commit()

# --- Library-Schema prüfen/migrieren (idempotent) ---
def ensure_library_schema(owner_user_id: Optional[int] = None):
    with _conn() as con:
        cur = con.cursor()
        if not _table_exists(cur, "library"):
            cur.executescript(LIB_SCHEMA_V2); con.commit(); return
        cur.execute("PRAGMA table_info(library);")
        cols = {row[1] for row in cur.fetchall()}
        if "user_id" not in cols and owner_user_id is not None:
            con.execute("ALTER TABLE library RENAME TO library_old;")
            con.executescript(LIB_SCHEMA_V2)
            con.execute("""
                INSERT INTO library (user_id, game_id, title, price, purchased_at)
                SELECT ?, game_id, title, price, purchased_at FROM library_old;
            """, (int(owner_user_id),))
            con.execute("DROP TABLE library_old;")
            con.commit()
            return
        if "title" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "price" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN price REAL NOT NULL DEFAULT 0.0")
        if "purchased_at" not in cols:
            cur.execute("ALTER TABLE library ADD COLUMN purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_library_user ON library(user_id)")
        con.commit()

# --- Init & Migration ---
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
            cur.executescript(LIB_SCHEMA_V2); con.commit(); return
        if _library_has_user_id(cur):
            return
        cur.execute("ALTER TABLE library RENAME TO library_old;")
        cur.executescript(LIB_SCHEMA_V2)
        cur.execute("""
            INSERT INTO library (user_id, game_id, title, price, purchased_at)
            SELECT ?, game_id, title, price, purchased_at FROM library_old;
        """, (int(owner_user_id),))
        cur.execute("DROP TABLE library_old;")
        con.commit()

# --- Library (user-spezifisch) ---
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
            SELECT game_id, title, price, purchased_at
            FROM library
            WHERE user_id=?
            ORDER BY purchased_at DESC;
        """, (int(uid),))
        return [
            {"id": int(gid), "title": title, "price": float(price), "purchased_at": ts}
            for gid, title, price, ts in cur.fetchall()
        ]

def add_to_library(game: Dict):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_library_schema(uid)
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO library (user_id, game_id, title, price) VALUES (?, ?, ?, ?);",
            (int(uid), int(game["id"]), game["title"], float(game["price"]))
        )
        con.commit()

def add_many_to_library(games: Iterable[Dict]):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_library_schema(uid)
    rows = [(int(uid), int(g["id"]), g["title"], float(g["price"])) for g in games]
    if not rows:
        return
    with _conn() as con:
        cur = con.cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO library (user_id, game_id, title, price) VALUES (?, ?, ?, ?);",
            rows
        )
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

# --- Cart (user-spezifisch) ---
def cart_get_items() -> List[Dict]:
    uid = _current_user_id()
    if uid is None:
        return []
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT game_id, title, price, added_at
            FROM cart
            WHERE user_id=?
            ORDER BY added_at DESC;
        """, (int(uid),))
        return [{"id": int(i), "title": t, "price": float(p), "added_at": a} for (i, t, p, a) in cur.fetchall()]

def cart_get_ids() -> Set[int]:
    return {int(x["id"]) for x in cart_get_items()}

def cart_add(game: Dict):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO cart (user_id, game_id, title, price) VALUES (?, ?, ?, ?);",
            (int(uid), int(game["id"]), game["title"], float(game["price"]))
        )
        con.commit()

def cart_add_many(games: Iterable[Dict]):
    uid = _current_user_id()
    if uid is None:
        raise RuntimeError("Kein Nutzer eingeloggt.")
    rows = [(int(uid), int(g["id"]), g["title"], float(g["price"])) for g in games]
    if not rows:
        return
    ensure_cart_schema()
    with _conn() as con:
        cur = con.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO cart (user_id, game_id, title, price) VALUES (?, ?, ?, ?);",
            rows
        )
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
        rows = [(int(uid), int(g["id"]), g["title"], float(g["price"])) for g in games]
        if rows:
            cur.executemany(
                "INSERT OR REPLACE INTO cart (user_id, game_id, title, price) VALUES (?, ?, ?, ?);",
                rows
            )
        con.commit()

# --- Session-Persistenz ---
SESSION_PATH = Path(__file__).resolve().parent / "session.json"

def save_session():
    if is_logged_in() and getattr(session.current_user, "id", None) is not None:
        SESSION_PATH.write_text(json.dumps({"user_id": int(session.current_user.id)}))
    else:
        clear_session()

def clear_session():
    try:
        SESSION_PATH.unlink()
    except FileNotFoundError:
        pass

def load_session() -> bool:
    if not SESSION_PATH.exists() or not auth_service:
        return False
    try:
        data = json.loads(SESSION_PATH.read_text())
        uid = int(data.get("user_id"))
        u = auth_service.get_user_by_id(uid)
        if u:
            session.current_user = u
            return True
    except Exception:
        pass
    clear_session()
    return False
