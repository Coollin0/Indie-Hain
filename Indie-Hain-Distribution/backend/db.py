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
                created_at TEXT
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT
            )
            """
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
