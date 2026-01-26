import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "indiehain.db"
STORAGE_CHUNKS = Path(__file__).resolve().parent / "storage" / "chunks"
STORAGE_APPS = Path(__file__).resolve().parent / "storage" / "apps"


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_schema():
    STORAGE_CHUNKS.mkdir(parents=True, exist_ok=True)
    STORAGE_APPS.mkdir(parents=True, exist_ok=True)

    with get_db() as db:
        # Grundtabellen
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                owner_user_id INTEGER,
                created_at TEXT,
                price REAL DEFAULT 0.0,
                description TEXT,
                cover_url TEXT
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                username TEXT,
                avatar_url TEXT,
                created_at TEXT
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT,
                refresh_token_hash TEXT NOT NULL,
                created_at TEXT,
                last_used_at TEXT,
                refresh_expires_at TEXT,
                revoked_at TEXT
            )
            """
        )

        session_cols = [r[1] for r in db.execute("PRAGMA table_info(sessions)").fetchall()]
        if "token" in session_cols and "id" not in session_cols:
            db.execute("ALTER TABLE sessions RENAME TO sessions_old")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    device_id TEXT,
                    refresh_token_hash TEXT NOT NULL,
                    created_at TEXT,
                    last_used_at TEXT,
                    refresh_expires_at TEXT,
                    revoked_at TEXT
                )
                """
            )
            db.execute("DROP TABLE sessions_old")
        else:
            if "device_id" not in session_cols:
                db.execute("ALTER TABLE sessions ADD COLUMN device_id TEXT")
            if "refresh_token_hash" not in session_cols:
                db.execute("ALTER TABLE sessions ADD COLUMN refresh_token_hash TEXT")
            if "last_used_at" not in session_cols:
                db.execute("ALTER TABLE sessions ADD COLUMN last_used_at TEXT")
            if "refresh_expires_at" not in session_cols:
                db.execute("ALTER TABLE sessions ADD COLUMN refresh_expires_at TEXT")
            if "revoked_at" not in session_cols:
                db.execute("ALTER TABLE sessions ADD COLUMN revoked_at TEXT")

        user_cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
        if "username" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if "avatar_url" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
        if "role" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "created_at" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        if "temp_password_hash" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN temp_password_hash TEXT")
        if "temp_password_plain" not in user_cols:
            db.execute("ALTER TABLE users ADD COLUMN temp_password_plain TEXT")
        if "force_password_reset" not in user_cols:
            db.execute(
                "ALTER TABLE users ADD COLUMN force_password_reset INTEGER NOT NULL DEFAULT 0"
            )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS builds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                version TEXT NOT NULL,
                platform TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                manifest_url TEXT,
                created_at TEXT
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                hash TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                ref_count INTEGER NOT NULL
            )
            """
        )

        # Spalten in apps nachrüsten (für bestehende DBs)
        cols = [r[1] for r in db.execute("PRAGMA table_info(apps)").fetchall()]

        if "is_approved" not in cols:
            db.execute(
                "ALTER TABLE apps ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 0"
            )

        if "price" not in cols:
            db.execute("ALTER TABLE apps ADD COLUMN price REAL DEFAULT 0.0")

        if "description" not in cols:
            db.execute("ALTER TABLE apps ADD COLUMN description TEXT")

        if "cover_url" not in cols:
            db.execute("ALTER TABLE apps ADD COLUMN cover_url TEXT")

        # Rabatt-Prozent für Sales
        if "sale_percent" not in cols:
            db.execute(
                "ALTER TABLE apps ADD COLUMN sale_percent REAL NOT NULL DEFAULT 0.0"
            )

        # Submissions für Admin-Review
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                app_slug TEXT NOT NULL,
                version TEXT NOT NULL,
                platform TEXT NOT NULL,
                channel TEXT NOT NULL,
                manifest_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Käufe (für Dev-Stats & Buyers-Liste)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                price REAL NOT NULL,
                purchased_at TEXT NOT NULL
            )
            """
        )

        # Extra-Bilder / Screenshots pro App (für späteres UI)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS app_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                image_url TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        db.commit()
