import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
import hashlib, os, hmac, shutil

DB_PATH = Path("data/auth.db")
AVATAR_DIR = Path("data/avatars")

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    username TEXT,
    avatar_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000)
    return salt.hex() + ":" + dk.hex()

def _verify_password(password: str, stored: str) -> bool:
    salt_hex, dk_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    new = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000).hex()
    return hmac.compare_digest(new, dk_hex)

@dataclass
class User:
    id: int
    email: str
    role: str
    username: str
    avatar_path: Optional[str] = None

@dataclass
class UserRow(User):
    created_at: str = ""

_ROLES = {"user", "dev", "admin"}

class AuthService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_schema()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(SCHEMA)
            cur = con.cursor()
            cur.execute("PRAGMA table_info(users);")
            cols = {row[1] for row in cur.fetchall()}
            if "username" not in cols:
                cur.execute("ALTER TABLE users ADD COLUMN username TEXT;")
            if "avatar_path" not in cols:
                cur.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT;")
            con.commit()
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- Public API ----------
    def register(self, email: str, password: str, username: str, avatar_src_path: Optional[str] = None) -> User:
        if not username.strip():
            raise ValueError("Benutzername ist erforderlich.")
        ph = _hash_password(password)
        with self._conn() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO users (email, password_hash, role, username) VALUES (?,?, 'user', ?)",
                (email, ph, username.strip())
            )
            uid = cur.lastrowid
            avatar_dest_str: Optional[str] = None
            if avatar_src_path:
                try:
                    src = Path(avatar_src_path)
                    ext = (src.suffix or ".png").lower()
                    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                        ext = ".png"
                    dest = AVATAR_DIR / f"{uid}{ext}"
                    shutil.copyfile(src, dest)
                    avatar_dest_str = str(dest)
                    cur.execute("UPDATE users SET avatar_path=? WHERE id=?", (avatar_dest_str, uid))
                except Exception:
                    avatar_dest_str = None
            cur.execute("SELECT id, email, role, username, avatar_path FROM users WHERE id=?", (uid,))
            r = cur.fetchone()
        return User(*r)

    def login(self, email: str, password: str) -> Optional[User]:
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("SELECT id, email, role, username, avatar_path, password_hash FROM users WHERE email=?", (email,))
            row = cur.fetchone()
            if not row:
                return None
            uid, em, role, uname, avatar, ph = row
            if _verify_password(password, ph):
                return User(uid, em, role, uname or "", avatar)
            return None

    def update_profile(self, user_id: int, username: Optional[str] = None, avatar_src_path: Optional[str] = None) -> User:
        with self._conn() as con:
            cur = con.cursor()
            if username is not None:
                if not username.strip():
                    raise ValueError("Benutzername darf nicht leer sein.")
                cur.execute("UPDATE users SET username=? WHERE id=?", (username.strip(), int(user_id)))
            if avatar_src_path:
                try:
                    src = Path(avatar_src_path)
                    ext = (src.suffix or ".png").lower()
                    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                        ext = ".png"
                    dest = AVATAR_DIR / f"{int(user_id)}{ext}"
                    shutil.copyfile(src, dest)
                    cur.execute("UPDATE users SET avatar_path=? WHERE id=?", (str(dest), int(user_id)))
                except Exception:
                    pass
            cur.execute("SELECT id, email, role, username, avatar_path FROM users WHERE id=?", (int(user_id),))
            r = cur.fetchone()
            if not r:
                raise ValueError("User nicht gefunden")
        return User(*r)

    def upgrade_to_dev(self, user_id: int) -> User:
        return self.set_role(user_id, "dev")

    def set_admin(self, email: str):
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("UPDATE users SET role='admin' WHERE email=?", (email,))

    def list_users(self) -> List[UserRow]:
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("SELECT id, email, role, username, avatar_path, created_at FROM users ORDER BY created_at DESC;")
            rows = cur.fetchall()
        return [UserRow(int(i), e, r, u or "", a, c) for (i, e, r, u, a, c) in rows]

    def set_role(self, user_id: int, role: str) -> User:
        if role not in {"user", "dev", "admin"}:
            raise ValueError(f"Ungültige Rolle: {role}")
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("UPDATE users SET role=? WHERE id=?", (role, int(user_id)))
            cur.execute("SELECT id, email, role, username, avatar_path FROM users WHERE id=?", (int(user_id),))
            r = cur.fetchone()
            if not r:
                raise ValueError("User nicht gefunden")
        return User(*r)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("SELECT id, email, role, username, avatar_path FROM users WHERE id=?", (int(user_id),))
            r = cur.fetchone()
            return User(*r) if r else None
