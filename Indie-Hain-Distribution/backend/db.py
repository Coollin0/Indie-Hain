from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).with_name("indiehain.db")
STORAGE_DIR = Path(__file__).with_name("storage")
STORAGE_APPS = STORAGE_DIR / "apps"
STORAGE_CHUNKS = STORAGE_DIR / "chunks"

for p in (STORAGE_DIR, STORAGE_APPS, STORAGE_CHUNKS):
    p.mkdir(parents=True, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    owner_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL,
    version TEXT NOT NULL,
    platform TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    manifest_url TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    hash TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    ref_count INTEGER NOT NULL DEFAULT 1
);
"""

with get_db() as db:
    db.executescript(SCHEMA)