# backend/main.py
from fastapi import FastAPI, HTTPException, Body, Depends
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from datetime import datetime
import hashlib, json

from .db import get_db, STORAGE_CHUNKS, STORAGE_APPS
from .models import AppCreate, BuildCreate, MissingChunksRequest, Manifest
from .auth import require_dev, require_user

app = FastAPI(title="Indie-Hain Distribution API")

def hex_shard(h: str) -> Path:
    return STORAGE_CHUNKS / h[0:2] / h[2:4] / h

def ensure_parent(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

# Apps anlegen
@app.post("/api/dev/apps")
async def create_app(
    payload: AppCreate,
    user: dict = Depends(require_dev),
):
    with get_db() as db:
        db.execute(
            "INSERT INTO apps(slug,title,owner_user_id,created_at) VALUES(?,?,?,?)",
            (payload.slug, payload.title, user["user_id"], datetime.utcnow().isoformat()),
        )
        db.commit()
        app_id = db.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    return {"id": app_id}

# Build anlegen
@app.post("/api/dev/builds")
async def create_build(
    payload: BuildCreate,
    user: dict = Depends(require_dev),
):
    with get_db() as db:
        row = db.execute("SELECT id FROM apps WHERE id=?", (payload.app_id,)).fetchone()
        if not row:
            raise HTTPException(404, "App not found")
        db.execute(
            """
            INSERT INTO builds(app_id,version,platform,channel,status,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (payload.app_id, payload.version, payload.platform, payload.channel, "draft", datetime.utcnow().isoformat()),
        )
        db.commit()
        build_id = db.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    return {"id": build_id}

# Fehlende Chunks abfragen
@app.post("/api/dev/builds/{build_id}/missing-chunks")
async def missing_chunks(
    build_id: int,
    req: MissingChunksRequest,
    user: dict = Depends(require_dev),
):
    missing = []
    for h in req.hashes:
        if not hex_shard(h).exists():
            missing.append(h)
    return {"missing": missing}

# Chunk hochladen (raw body)
@app.post("/api/dev/chunk/{hash}")
async def upload_chunk(
    hash: str,
    body: bytes = Body(...),
    user: dict = Depends(require_dev),
):
    calc = hashlib.sha256(body).hexdigest()
    if calc != hash:
        raise HTTPException(400, "Hash mismatch")
    p = hex_shard(hash)
    ensure_parent(p)
    p.write_bytes(body)
    from .db import get_db, STORAGE_CHUNKS
    with get_db() as db:
        row = db.execute("SELECT hash FROM chunks WHERE hash=?", (hash,)).fetchone()
        if row:
            db.execute("UPDATE chunks SET ref_count=ref_count+1 WHERE hash=?", (hash,))
        else:
            db.execute(
                "INSERT INTO chunks(hash,size,storage_path,ref_count) VALUES(?,?,?,1)",
                (hash, len(body), str(p.relative_to(STORAGE_CHUNKS.parent))),
            )
        db.commit()
    return {"ok": True}

# Build finalisieren (Manifest speichern)
@app.post("/api/dev/builds/{build_id}/finalize")
async def finalize_build(
    build_id: int,
    manifest: Manifest,
    user: dict = Depends(require_dev),
):
    from .db import get_db
    with get_db() as db:
        b = db.execute("SELECT * FROM builds WHERE id=?", (build_id,)).fetchone()
        if not b:
            raise HTTPException(404, "Build not found")
        a = db.execute("SELECT * FROM apps WHERE id=?", (b["app_id"],)).fetchone()
        if not a:
            raise HTTPException(404, "App not found")
    manifest_rel = Path(f"apps/{manifest.app}/builds/{manifest.version}/{manifest.platform}/{manifest.channel}/manifest.json")
    manifest_path = STORAGE_APPS.parent / manifest_rel
    ensure_parent(manifest_path)
    manifest_path.write_text(json.dumps(manifest.dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    with get_db() as db:
        db.execute("UPDATE builds SET status=?, manifest_url=? WHERE id=?", ("ready", str(manifest_rel), build_id))
        db.commit()
    return {"manifest_url": str(manifest_rel)}

# Manifest als JSON (nicht FileResponse) – kompatibel mit downloader.py (.json())
@app.get("/api/manifest/{slug}/{platform}/{channel}")
async def get_manifest(
    slug: str,
    platform: str,
    channel: str,
    user: dict = Depends(require_user),
):
    with get_db() as db:
        row = db.execute(
            """
            SELECT b.manifest_url FROM builds b
            JOIN apps a ON a.id=b.app_id
            WHERE a.slug=? AND b.platform=? AND b.channel=? AND b.status='ready'
            ORDER BY b.id DESC LIMIT 1
            """,
            (slug, platform, channel),
        ).fetchone()
        if not row:
            raise HTTPException(404, "No manifest")
    manifest_path = STORAGE_APPS.parent / Path(row["manifest_url"])
    if not manifest_path.exists():
        raise HTTPException(404, "Manifest missing on disk")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return JSONResponse(content=data)

# Chunks/Apps ausliefern (MVP)
@app.get("/storage/chunks/{hash}")
async def get_chunk(hash: str, user: dict = Depends(require_user)):
    p = STORAGE_CHUNKS / hash[0:2] / hash[2:4] / hash
    if not p.exists():
        raise HTTPException(404, "Chunk not found")
    return FileResponse(p)

@app.get("/storage/apps/{path:path}")
async def get_storage_file(path: str, user: dict = Depends(require_user)):
    p = STORAGE_APPS / path
    if not p.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(p)
