# backend/main.py
from fastapi import FastAPI, HTTPException, Body, Depends, APIRouter, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Iterator, Optional
from pathlib import Path
from datetime import datetime
import hashlib, json, io, zipfile, tempfile, os

from .auth import (
    require_dev,
    require_user,
    require_admin,
    authenticate,
    create_user,
    issue_token,
    update_username,
    set_role_by_email,
    set_role_by_id,
    update_avatar_url,
)
from .db import get_db, STORAGE_CHUNKS, STORAGE_APPS, ensure_schema
from .models import (
    AppCreate,
    BuildCreate,
    MissingChunksRequest,
    Manifest,
    AppMetaUpdate,
    PurchaseReport,
    AuthRegister,
    AuthLogin,
    AuthProfileUpdate,
    AuthBootstrap,
    AdminRoleUpdate,
)
from pathlib import Path as _Path

ensure_schema()

app = FastAPI(title="Indie-Hain Distribution API")

_static = _Path(__file__).resolve().parent / "static"
(_static / "covers").mkdir(parents=True, exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(_Path(__file__).resolve().parent / "static")),
    name="static",
)

# Router für Admin & Public APIs
admin = APIRouter(prefix="/api/admin", tags=["admin"])
public = APIRouter(prefix="/api/public", tags=["public"])


# ===============================
# Auth API
# ===============================

@app.post("/api/auth/register")
def auth_register(payload: AuthRegister):
    user = create_user(payload.email, payload.password, payload.username)
    token = issue_token(user["id"])
    return {
        "token": token,
        "user": user,
    }


@app.post("/api/auth/login")
def auth_login(payload: AuthLogin):
    user = authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = issue_token(user["id"])
    return {
        "token": token,
        "user": user,
    }


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_user)):
    return {"user": {
        "id": int(user["user_id"]),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
        "username": user.get("username", ""),
        "avatar_url": user.get("avatar_url", ""),
    }}


@app.post("/api/auth/profile")
def auth_profile(payload: AuthProfileUpdate, user: dict = Depends(require_user)):
    if payload.username is None:
        return {"user": {
            "id": int(user["user_id"]),
            "email": user.get("email", ""),
            "role": user.get("role", "user"),
            "username": user.get("username", ""),
            "avatar_url": user.get("avatar_url", ""),
        }}
    updated = update_username(user["user_id"], payload.username)
    return {"user": updated}


@app.post("/api/auth/upgrade/dev")
def auth_upgrade_dev(user: dict = Depends(require_user)):
    updated = set_role_by_id(user["user_id"], "dev")
    return {"user": updated}


@app.post("/api/auth/avatar")
async def auth_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    static_dir = Path(__file__).resolve().parent / "static" / "avatars"
    static_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix or ".png"
    if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        ext = ".png"
    dst = static_dir / f"{int(user['user_id'])}{ext}"
    with dst.open("wb") as out:
        out.write(await file.read())
    avatar_url = f"/static/avatars/{dst.name}"
    updated = update_avatar_url(user["user_id"], avatar_url)
    return {"user": updated}


@app.post("/api/auth/bootstrap-admin")
def auth_bootstrap_admin(payload: AuthBootstrap):
    secret = os.environ.get("ADMIN_BOOTSTRAP_SECRET", "")
    if not secret or payload.secret != secret:
        raise HTTPException(403, "Bootstrap disabled or invalid secret")
    user = set_role_by_email(payload.email, "admin")
    return {"user": user}


@admin.get("/users")
def admin_list_users(user=Depends(require_admin)):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, email, role, username, avatar_url, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": int(r["id"]),
            "email": r["email"],
            "role": (r["role"] or "user").lower(),
            "username": r["username"] or "",
            "avatar_url": r["avatar_url"] or "",
            "created_at": r["created_at"],
        })
    return {"items": items}


@admin.post("/users/{user_id}/role")
def admin_set_role(user_id: int, payload: AdminRoleUpdate, user=Depends(require_admin)):
    role = (payload.role or "user").lower()
    if role not in ("user", "dev", "admin"):
        raise HTTPException(400, "invalid role")
    updated = set_role_by_id(user_id, role)
    return {"user": updated}


# ===============================
# Hilfsfunktionen
# ===============================
def hex_shard(h: str) -> Path:
    return STORAGE_CHUNKS / h[0:2] / h[2:4] / h


def ensure_parent(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def _read_chunk_bytes(hash_hex: str) -> bytes:
    p = STORAGE_CHUNKS / hash_hex[0:2] / hash_hex[2:4] / hash_hex
    if not p.exists():
        raise HTTPException(404, f"Chunk {hash_hex} missing")
    return p.read_bytes()


# ===============================
# Developer API
# ===============================

# App anlegen
@app.post("/api/dev/apps")
async def create_app(payload: AppCreate, user: dict = Depends(require_dev)):
    with get_db() as db:
        db.execute(
            "INSERT INTO apps(slug,title,owner_user_id,created_at) VALUES(?,?,?,?)",
            (payload.slug, payload.title, user["user_id"], datetime.utcnow().isoformat()),
        )
        db.commit()
        app_id = db.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    return {"id": app_id}


# App-Metadaten aktualisieren (Preis, Beschreibung, Cover, Rabatt)
@app.post("/api/dev/apps/{slug}/meta")
async def update_app_meta(slug: str, payload: AppMetaUpdate, user: dict = Depends(require_dev)):
    with get_db() as db:
        row = db.execute("SELECT id FROM apps WHERE slug=?", (slug,)).fetchone()
        if not row:
            raise HTTPException(404, "App not found")

        fields = []
        values = []

        if payload.title is not None:
            fields.append("title=?")
            values.append(payload.title)

        if payload.price is not None:
            fields.append("price=?")
            values.append(payload.price)

        if payload.description is not None:
            fields.append("description=?")
            values.append(payload.description)

        if payload.cover_url is not None:
            fields.append("cover_url=?")
            values.append(payload.cover_url)

        if payload.sale_percent is not None:
            fields.append("sale_percent=?")
            values.append(payload.sale_percent)

        if not fields:
            return {"ok": True, "note": "nothing_to_update"}

        values.append(slug)
        sql = "UPDATE apps SET " + ", ".join(fields) + " WHERE slug=?"
        db.execute(sql, values)
        db.commit()

    return {"ok": True}



@app.post("/api/dev/apps/{slug}/cover")
async def upload_app_cover(
    slug: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_dev),
):
    static_dir = Path(__file__).resolve().parent / "static" / "covers"
    static_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix or ".jpg"
    dst = static_dir / f"{slug}{ext}"
    with dst.open("wb") as out:
        out.write(await file.read())
    cover_url = f"/static/covers/{dst.name}"
    with get_db() as db:
        db.execute("UPDATE apps SET cover_url=? WHERE slug=?", (cover_url, slug))
        db.commit()
    return {"cover_url": cover_url}


# Build anlegen
@app.post("/api/dev/builds")
async def create_build(payload: BuildCreate, user: dict = Depends(require_dev)):
    with get_db() as db:
        row = db.execute("SELECT id FROM apps WHERE id=?", (payload.app_id,)).fetchone()
        if not row:
            raise HTTPException(404, "App not found")
        db.execute(
            """
            INSERT INTO builds(app_id,version,platform,channel,status,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (
                payload.app_id,
                payload.version,
                payload.platform,
                payload.channel,
                "draft",
                datetime.utcnow().isoformat(),
            ),
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


# Build finalisieren (Manifest speichern + Submission erzeugen)
@app.post("/api/dev/builds/{build_id}/finalize")
async def finalize_build(
    build_id: int,
    manifest: Manifest,
    user: dict = Depends(require_dev),
):
    with get_db() as db:
        b = db.execute("SELECT * FROM builds WHERE id=?", (build_id,)).fetchone()
        if not b:
            raise HTTPException(404, "Build not found")
        a = db.execute("SELECT * FROM apps WHERE id=?", (b["app_id"],)).fetchone()
        if not a:
            raise HTTPException(404, "App not found")

    manifest_rel = Path(
        f"apps/{manifest.app}/builds/{manifest.version}/{manifest.platform}/{manifest.channel}/manifest.json"
    )
    manifest_path = STORAGE_APPS.parent / manifest_rel
    ensure_parent(manifest_path)
    manifest_path.write_text(
        json.dumps(manifest.dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with get_db() as db:
        db.execute(
            "UPDATE builds SET status=?, manifest_url=? WHERE id=?",
            ("ready", str(manifest_rel), build_id),
        )
        db.commit()

    # Admin-Review-Eintrag erzeugen
    with get_db() as db:
        db.execute(
            """
            INSERT INTO submissions (user_id, app_slug, version, platform, channel, manifest_url, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                user["user_id"],
                manifest.app,
                manifest.version,
                manifest.platform,
                manifest.channel,
                str(manifest_rel),
            ),
        )
        db.commit()

    return {"manifest_url": str(manifest_rel)}


# =============== NEU: Dev-Overview "Meine Apps" =================

@app.get("/api/dev/my-apps")
async def get_my_apps(user: dict = Depends(require_dev)):
    """Liste aller Apps des aktuellen Devs inkl. purchase_count."""
    with get_db() as db:
        rows = db.execute(
            """
            SELECT a.*,
                   COALESCE((
                       SELECT COUNT(*) FROM purchases p WHERE p.app_id = a.id
                   ), 0) AS purchase_count
            FROM apps a
            WHERE a.owner_user_id = ?
            ORDER BY a.created_at DESC
            """,
            (user["user_id"],),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/dev/apps/{app_id}/purchases")
async def dev_app_purchases(app_id: int, user: dict = Depends(require_dev)):
    """Buyers-Liste für eine App (user_id, price, purchased_at)."""
    with get_db() as db:
        owner = db.execute(
            "SELECT owner_user_id FROM apps WHERE id=?", (app_id,)
        ).fetchone()
        if not owner:
            raise HTTPException(404, "App not found")
        if owner["owner_user_id"] != user["user_id"]:
            raise HTTPException(403, "Not your app")

        rows = db.execute(
            """
            SELECT id, app_id, user_id, price, purchased_at
            FROM purchases
            WHERE app_id = ?
            ORDER BY purchased_at DESC
            """,
            (app_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# =============== NEU: User-Käufe melden =========================

@app.post("/api/user/purchases/report")
async def report_purchase(
    payload: PurchaseReport,
    user: dict = Depends(require_user),
):
    """Launcher meldet einen Kauf an den Distribution-Server."""
    with get_db() as db:
        db.execute(
            """
            INSERT INTO purchases(app_id, user_id, price, purchased_at)
            VALUES(?,?,?,?)
            """,
            (
                payload.app_id,
                user["user_id"],
                float(payload.price),
                datetime.utcnow().isoformat(),
            ),
        )
        db.commit()
    return {"ok": True}


# ===============================
# Manifest & Storage
# ===============================

# Manifest abrufen (JSONResponse)
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


# Dateien / Chunks ausliefern
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


# ===============================
# Admin API
# ===============================

@admin.get("/submissions")
def list_submissions(status: str | None = None, user=Depends(require_admin)):
    q = "SELECT * FROM submissions"
    params = []
    if status:
        q += " WHERE status=?"
        params.append(status)
    with get_db() as db:
        rows = [dict(r) for r in db.execute(q, params).fetchall()]
    return {"items": rows}


@admin.get("/submissions/{sid}/manifest")
def get_submission_manifest(sid: int, user=Depends(require_admin)):
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = STORAGE_APPS.parent / s["manifest_url"]
    return json.loads(mpath.read_text(encoding="utf-8"))


@admin.post("/submissions/{sid}/approve")
def approve_submission(sid: int, user=Depends(require_admin)):
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
        if s["status"] != "pending":
            raise HTTPException(400, "Already processed")

        db.execute("UPDATE apps SET is_approved=1 WHERE slug=?", (s["app_slug"],))
        db.execute("UPDATE submissions SET status='approved' WHERE id=?", (sid,))
        db.commit()
    return {"ok": True}


@admin.post("/submissions/{sid}/reject")
def reject_submission(
    sid: int,
    note: str | None = None,
    user=Depends(require_admin),
):
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
        db.execute(
            "UPDATE submissions SET status='rejected', note=? WHERE id=?", (note, sid)
        )
        db.commit()
    return {"ok": True}


def _read_chunk(hash_hex: str) -> bytes:
    p = STORAGE_CHUNKS / hash_hex[0:2] / hash_hex[2:4] / hash_hex
    if not p.exists():
        raise HTTPException(404, f"Chunk {hash_hex} missing")
    return p.read_bytes()


@admin.get("/submissions/{sid}/files")
def list_submission_files(sid: int, user=Depends(require_admin)):
    # Liefert die Datei-Liste (aus dem Manifest)
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = STORAGE_APPS.parent / s["manifest_url"]
    m = json.loads(mpath.read_text(encoding="utf-8"))
    files = m.get("files", [])
    return {"files": files, "app": m.get("app"), "version": m.get("version")}


@admin.get("/submissions/{sid}/files/download")
def download_submission_file(sid: int, path: str, user=Depends(require_admin)):
    # Baut eine Datei aus den Chunks zusammen und streamt sie
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = STORAGE_APPS.parent / s["manifest_url"]
    m = json.loads(mpath.read_text(encoding="utf-8"))
    f = next((x for x in m.get("files", []) if x.get("path") == path), None)
    if not f:
        raise HTTPException(404, "File not in manifest")

    def _iter() -> Iterator[bytes]:
        import hashlib as _hl

        file_hasher = _hl.sha256()
        for ch in f["chunks"]:
            data = _read_chunk(ch["sha256"])
            # einfache Konsistenzprüfung:
            if _hl.sha256(data).hexdigest() != ch["sha256"]:
                raise HTTPException(409, "Chunk hash mismatch")
            file_hasher.update(data)
            yield data
        # Optional: End-to-End Hash prüfen
        if f.get("sha256") and file_hasher.hexdigest() != f["sha256"]:
            # Warnen durch Header statt Abbruch wäre auch möglich
            raise HTTPException(409, "File hash mismatch")

    filename = Path(path).name
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(_iter(), headers=headers, media_type="application/octet-stream")


@admin.post("/submissions/{sid}/files/verify")
def verify_submission_file(sid: int, path: str, user=Depends(require_admin)):
    # Prüft Chunk-Hashes und den finalen Datei-Hash
    import hashlib as _hl

    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = STORAGE_APPS.parent / s["manifest_url"]
    m = json.loads(mpath.read_text(encoding="utf-8"))
    f = next((x for x in m.get("files", []) if x.get("path") == path), None)
    if not f:
        raise HTTPException(404, "File not in manifest")

    chunk_ok = True
    for ch in f["chunks"]:
        if _hl.sha256(_read_chunk(ch["sha256"])).hexdigest() != ch["sha256"]:
            chunk_ok = False
            break

    file_ok = False
    if chunk_ok:
        fh = _hl.sha256()
        for ch in f["chunks"]:
            fh.update(_read_chunk(ch["sha256"]))
        file_ok = fh.hexdigest() == f.get("sha256")

    return {"chunk_ok": chunk_ok, "file_ok": file_ok, "expected": f.get("sha256")}


@admin.get("/submissions/{sid}/files/zip")
def download_submission_zip(sid: int, user=Depends(require_admin)):
    # 1) Submission + Manifest laden
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = STORAGE_APPS.parent / s["manifest_url"]
    m = json.loads(mpath.read_text(encoding="utf-8"))
    files = m.get("files", [])
    app_name = m.get("app", "app")
    version = m.get("version", "0.0.0")

    # 2) ZIP in einer temporären Datei erzeugen (robust für große Builds)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    tmp.close()
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                relpath = f.get("path")
                if not relpath:
                    continue
                # Datei aus Chunks rekonstruieren
                bio = io.BytesIO()
                for ch in f.get("chunks", []):
                    data = _read_chunk_bytes(ch["sha256"])
                    bio.write(data)
                bio.seek(0)
                # ins ZIP schreiben (Pfad wie im Manifest)
                zf.writestr(relpath, bio.read())

        # 3) Datei als Stream zurückgeben und danach löschen
        def _iter():
            with open(tmp_path, "rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        filename = f"{app_name}-{version}.zip"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(_iter(), headers=headers, media_type="application/zip")
    except:
        # Cleanup bei Fehler
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


# ===============================
# Öffentliche (Public) API
# ===============================

@public.get("/catalog")
def catalog():
    with get_db() as db:
        apps = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM apps WHERE is_approved=1 ORDER BY id DESC"
            ).fetchall()
        ]
    return {"apps": apps}


@public.get("/apps")
def list_public_apps():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                a.id,
                a.slug,
                a.title,
                COALESCE(a.price, 0.0)         AS price,
                COALESCE(a.description, '')    AS description,
                COALESCE(a.cover_url, '')      AS cover_url,
                COALESCE(a.sale_percent, 0.0)  AS sale_percent,
                COALESCE((
                    SELECT COUNT(*) FROM purchases p WHERE p.app_id = a.id
                ), 0) AS purchase_count
            FROM apps a
            WHERE a.is_approved = 1
            ORDER BY a.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]

@public.get("/apps/{app_id}")
def get_public_app(app_id: int):
    """
    Einzelnes Game für Shop/Library nach ID.
    """
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                a.id,
                a.slug,
                a.title,
                COALESCE(a.price, 0.0)         AS price,
                COALESCE(a.description, '')    AS description,
                COALESCE(a.cover_url, '')      AS cover_url,
                COALESCE(a.sale_percent, 0.0)  AS sale_percent,
                COALESCE((
                    SELECT COUNT(*) FROM purchases p WHERE p.app_id = a.id
                ), 0) AS purchase_count
            FROM apps a
            WHERE a.is_approved = 1
              AND a.id = ?
            """,
            (app_id,),
        ).fetchone()

    if not row:
        raise HTTPException(404, "App not found")

    return dict(row)


# Router einbinden
app.include_router(admin)
app.include_router(public)
