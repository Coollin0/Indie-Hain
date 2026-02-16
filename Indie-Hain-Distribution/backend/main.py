# backend/main.py
from fastapi import FastAPI, HTTPException, Body, Depends, APIRouter, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Iterator, Optional
from pathlib import Path, PurePosixPath
from datetime import datetime, timedelta
import hashlib, json, io, zipfile, tempfile, os, re, secrets

from .auth import (
    require_dev,
    require_user,
    require_admin,
    authenticate,
    authenticate_username,
    create_user,
    issue_tokens,
    refresh_tokens,
    update_username,
    set_role_by_email,
    set_role_by_id,
    update_avatar_url,
    revoke_session_by_id,
    revoke_session_by_refresh,
    session_id_from_access_token,
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
    AuthRefresh,
    AuthLogout,
    AdminRoleUpdate,
    AdminDevUpgradeGrant,
)
from pathlib import Path as _Path

ensure_schema()

app = FastAPI(title="Indie-Hain Distribution API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dashboard.indie-hain.corneliusgames.com",
        "https://indie-hain.corneliusgames.com",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

_static = _Path(__file__).resolve().parent / "static"
(_static / "covers").mkdir(parents=True, exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(_Path(__file__).resolve().parent / "static")),
    name="static",
)

DEV_UPGRADE_PRICE_EUR = float(os.environ.get("DEV_UPGRADE_PRICE_EUR", "20"))
PAYMENT_MODE = (os.environ.get("PAYMENT_MODE", "test") or "test").strip().lower()
if PAYMENT_MODE not in {"test", "live"}:
    PAYMENT_MODE = "test"

# Router für Admin & Public APIs
admin = APIRouter(prefix="/api/admin", tags=["admin"])
public = APIRouter(prefix="/api/public", tags=["public"])


# ===============================
# Auth API
# ===============================

@app.post("/api/auth/register")
def auth_register(payload: AuthRegister):
    user = create_user(payload.email, payload.password, payload.username)
    return issue_tokens(user, payload.device_id)


@app.post("/api/auth/login")
def auth_login(payload: AuthLogin):
    user = None
    if payload.email:
        user = authenticate(payload.email, payload.password)
    elif payload.username:
        user = authenticate_username(payload.username, payload.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return issue_tokens(user, payload.device_id)


@app.post("/api/auth/refresh")
def auth_refresh(payload: AuthRefresh):
    return refresh_tokens(payload.refresh_token, payload.device_id)


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
    current_role = str(user.get("role") or "user").lower()
    if current_role in ("dev", "admin"):
        return {
            "user": {
                "id": int(user["user_id"]),
                "email": user.get("email", ""),
                "role": current_role,
                "username": user.get("username", ""),
                "avatar_url": user.get("avatar_url", ""),
            },
            "upgrade": {"status": "already_enabled", "mode": PAYMENT_MODE},
        }

    user_id = int(user["user_id"])
    payment = _find_open_dev_upgrade_payment(user_id)
    if not payment:
        if PAYMENT_MODE == "test":
            payment_id = _create_dev_upgrade_payment(
                user_id=user_id,
                provider="stripe_test",
                payment_ref=f"test_{secrets.token_hex(8)}",
                note="auto test payment",
            )
            payment = {"id": payment_id, "provider": "stripe_test"}
        else:
            raise HTTPException(402, "DEV_UPGRADE_PAYMENT_REQUIRED")

    _consume_dev_upgrade_payment(int(payment["id"]), user_id)
    updated = set_role_by_id(user_id, "dev", revoke_sessions=False)
    return {
        "user": updated,
        "upgrade": {
            "status": "enabled",
            "mode": PAYMENT_MODE,
            "payment_id": int(payment["id"]),
            "provider": str(payment.get("provider") or ""),
        },
    }


@app.post("/api/auth/logout")
def auth_logout(payload: AuthLogout, authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        session_id = session_id_from_access_token(token)
        if session_id:
            revoke_session_by_id(session_id)
            return {"ok": True}
    if payload.refresh_token:
        revoke_session_by_refresh(payload.refresh_token)
        return {"ok": True}
    raise HTTPException(400, "Missing session")


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


@app.get("/api/health")
def health():
    return {"ok": True}


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
    updated = set_role_by_id(user_id, role, revoke_sessions=True)
    return {"user": updated}


@admin.post("/users/{user_id}/dev-upgrade/grant")
def admin_grant_dev_upgrade(
    user_id: int,
    payload: AdminDevUpgradeGrant | None = Body(default=None),
    user=Depends(require_admin),
):
    current_role = _get_user_role(user_id)
    if current_role is None:
        raise HTTPException(404, "user not found")
    if current_role == "admin":
        raise HTTPException(400, "target user is already admin")
    if current_role == "dev":
        updated = set_role_by_id(user_id, "dev", revoke_sessions=False)
        return {"user": updated, "grant": {"status": "already_dev"}}

    note = payload.note if payload else None
    payment_id = _create_dev_upgrade_payment(
        user_id=int(user_id),
        provider="admin_grant",
        amount=0.0,
        payment_ref=f"grant_{secrets.token_hex(8)}",
        note=note or f"Granted by admin #{int(user['user_id'])}",
    )
    _consume_dev_upgrade_payment(payment_id, int(user["user_id"]))
    updated = set_role_by_id(user_id, "dev", revoke_sessions=True)
    return {
        "user": updated,
        "grant": {
            "status": "granted",
            "payment_id": payment_id,
            "granted_by_user_id": int(user["user_id"]),
        },
    }


@admin.get("/overview")
def admin_overview(user=Depends(require_admin)):
    since_30d = (datetime.utcnow() - timedelta(days=30)).isoformat()
    with get_db() as db:
        user_total = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        role_rows = db.execute(
            "SELECT role, COUNT(*) AS c FROM users GROUP BY role"
        ).fetchall()
        role_counts = {(r["role"] or "user").lower(): r["c"] for r in role_rows}

        submission_rows = db.execute(
            "SELECT status, COUNT(*) AS c FROM submissions GROUP BY status"
        ).fetchall()
        submission_counts = {(r["status"] or "pending").lower(): r["c"] for r in submission_rows}
        submissions_total = sum(submission_counts.values())

        apps_total = db.execute("SELECT COUNT(*) AS c FROM apps").fetchone()["c"]
        apps_approved = db.execute(
            "SELECT COUNT(*) AS c FROM apps WHERE is_approved=1"
        ).fetchone()["c"]

        purchases_total = db.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(price), 0) AS total FROM purchases"
        ).fetchone()
        purchases_30d = db.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(price), 0) AS total FROM purchases WHERE purchased_at >= ?",
            (since_30d,),
        ).fetchone()

        last_user = db.execute("SELECT MAX(created_at) AS ts FROM users").fetchone()["ts"]
        last_submission = db.execute("SELECT MAX(created_at) AS ts FROM submissions").fetchone()["ts"]
        last_purchase = db.execute("SELECT MAX(purchased_at) AS ts FROM purchases").fetchone()["ts"]

    return {
        "users": {
            "total": user_total,
            "admins": role_counts.get("admin", 0),
            "devs": role_counts.get("dev", 0),
            "users": role_counts.get("user", 0),
        },
        "submissions": {
            "total": submissions_total,
            "pending": submission_counts.get("pending", 0),
            "approved": submission_counts.get("approved", 0),
            "rejected": submission_counts.get("rejected", 0),
        },
        "apps": {
            "total": apps_total,
            "approved": apps_approved,
            "pending": max(0, apps_total - apps_approved),
        },
        "purchases": {
            "total": purchases_total["c"],
            "revenue_total": float(purchases_total["total"] or 0),
            "count_30d": purchases_30d["c"],
            "revenue_30d": float(purchases_30d["total"] or 0),
        },
        "last_activity": {
            "user": last_user,
            "submission": last_submission,
            "purchase": last_purchase,
        },
        "since_30d": since_30d,
    }


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

SLUG_RE = re.compile(r"^[a-z0-9-]{1,64}$")
COMP_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _require_safe_slug(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise HTTPException(400, "Invalid slug")
    return slug


def _require_safe_comp(value: str, field: str) -> str:
    if not COMP_RE.match(value or ""):
        raise HTTPException(400, f"Invalid {field}")
    return value


def _require_sha256(value: str) -> str:
    if not SHA256_RE.match(value or ""):
        raise HTTPException(400, "Invalid sha256")
    return value


def _normalize_manifest_file_path(path: str) -> str:
    raw = (path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise HTTPException(400, "Invalid file path")
    pure = PurePosixPath(raw)
    parts = pure.parts
    if not parts:
        raise HTTPException(400, "Invalid file path")
    if any(part in ("", ".", "..") for part in parts):
        raise HTTPException(400, "Invalid file path")
    if ":" in parts[0]:
        raise HTTPException(400, "Invalid file path")
    normalized = "/".join(parts)
    if not normalized:
        raise HTTPException(400, "Invalid file path")
    return normalized


def _validate_manifest_files(manifest: Manifest) -> None:
    seen_paths: set[str] = set()
    total_size = 0
    for entry in manifest.files:
        normalized_path = _normalize_manifest_file_path(entry.path)
        if normalized_path in seen_paths:
            raise HTTPException(400, "Duplicate file path")
        seen_paths.add(normalized_path)
        entry.path = normalized_path

        _require_sha256(entry.sha256)
        expected_offset = 0
        for ch in entry.chunks:
            _require_sha256(ch.sha256)
            if int(ch.size) < 0:
                raise HTTPException(400, "Invalid chunk size")
            if int(ch.offset) != expected_offset:
                raise HTTPException(400, "Invalid chunk offsets")
            expected_offset += int(ch.size)
        if int(entry.size) != expected_offset:
            raise HTTPException(400, "File size mismatch")
        total_size += int(entry.size)

    if int(manifest.total_size) != total_size:
        raise HTTPException(400, "Manifest total_size mismatch")


def _safe_resolve(base: Path, rel: Path) -> Path:
    base_resolved = base.resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base_resolved):
        raise HTTPException(403, "Invalid path")
    return target


def _effective_price(price: float, sale_percent: float) -> float:
    base = max(0.0, float(price or 0.0))
    sale = min(100.0, max(0.0, float(sale_percent or 0.0)))
    return round(base * (100.0 - sale) / 100.0, 2)


def _create_dev_upgrade_payment(
    *,
    user_id: int,
    provider: str,
    amount: float = DEV_UPGRADE_PRICE_EUR,
    currency: str = "EUR",
    note: str | None = None,
    payment_ref: str | None = None,
) -> int:
    now_iso = datetime.utcnow().isoformat()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO dev_upgrade_payments(
                user_id, amount, currency, provider, payment_ref, note, created_at, paid_at
            )
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                int(user_id),
                float(amount),
                str(currency or "EUR").upper(),
                provider,
                payment_ref,
                note,
                now_iso,
                now_iso,
            ),
        )
        db.commit()
        row = db.execute("SELECT last_insert_rowid() AS id").fetchone()
    return int(row["id"])


def _find_open_dev_upgrade_payment(user_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            """
            SELECT id, user_id, amount, currency, provider, payment_ref, note, paid_at
            FROM dev_upgrade_payments
            WHERE user_id=? AND consumed_at IS NULL
            ORDER BY paid_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
    return dict(row) if row else None


def _consume_dev_upgrade_payment(payment_id: int, consumed_by_user_id: int) -> None:
    now_iso = datetime.utcnow().isoformat()
    with get_db() as db:
        cur = db.execute(
            """
            UPDATE dev_upgrade_payments
            SET consumed_at=?, consumed_by_user_id=?
            WHERE id=? AND consumed_at IS NULL
            """,
            (now_iso, int(consumed_by_user_id), int(payment_id)),
        )
        db.commit()
    if cur.rowcount != 1:
        raise HTTPException(409, "Upgrade payment already consumed")


def _get_user_role(user_id: int) -> str | None:
    with get_db() as db:
        row = db.execute(
            "SELECT role FROM users WHERE id=?",
            (int(user_id),),
        ).fetchone()
    if not row:
        return None
    return str(row["role"] or "user").lower()


def _latest_ready_manifest_rel(slug: str, platform: str, channel: str) -> str:
    _require_safe_slug(slug)
    _require_safe_comp(platform, "platform")
    _require_safe_comp(channel, "channel")
    with get_db() as db:
        row = db.execute(
            """
            SELECT b.manifest_url
            FROM builds b
            JOIN apps a ON a.id=b.app_id
            WHERE a.slug=? AND b.platform=? AND b.channel=? AND b.status='ready'
            ORDER BY b.id DESC LIMIT 1
            """,
            (slug, platform, channel),
        ).fetchone()
    if not row or not row["manifest_url"]:
        raise HTTPException(404, "No manifest")
    return str(row["manifest_url"])


def _manifest_rel_for_build(slug: str, version: str, platform: str, channel: str) -> str:
    _require_safe_slug(slug)
    _require_safe_comp(version, "version")
    _require_safe_comp(platform, "platform")
    _require_safe_comp(channel, "channel")
    with get_db() as db:
        row = db.execute(
            """
            SELECT b.manifest_url
            FROM builds b
            JOIN apps a ON a.id=b.app_id
            WHERE a.slug=? AND b.version=? AND b.platform=? AND b.channel=? AND b.status='ready'
            ORDER BY b.id DESC LIMIT 1
            """,
            (slug, version, platform, channel),
        ).fetchone()
    if not row or not row["manifest_url"]:
        raise HTTPException(404, "No manifest for build")
    return str(row["manifest_url"])


def _load_ready_manifest(
    slug: str,
    platform: str,
    channel: str,
    version: str | None = None,
) -> tuple[dict, str]:
    if version:
        manifest_rel = _manifest_rel_for_build(slug, version, platform, channel)
    else:
        manifest_rel = _latest_ready_manifest_rel(slug, platform, channel)
    manifest_path = _safe_resolve(STORAGE_APPS.parent, Path(manifest_rel))
    if not manifest_path.exists():
        raise HTTPException(404, "Manifest missing on disk")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, "Manifest invalid") from exc
    return data, manifest_rel


def _manifest_contains_chunk(manifest: dict, sha256: str) -> bool:
    for file_entry in manifest.get("files", []):
        for chunk in file_entry.get("chunks", []):
            if str(chunk.get("sha256", "")) == sha256:
                return True
    return False


def _require_download_access(slug: str, user: dict) -> dict:
    _require_safe_slug(slug)
    uid = int(user["user_id"])
    role = str(user.get("role") or "user").lower()
    with get_db() as db:
        app_row = db.execute(
            "SELECT id, owner_user_id, is_approved FROM apps WHERE slug=?",
            (slug,),
        ).fetchone()
        if not app_row:
            raise HTTPException(404, "App not found")
        app_id = int(app_row["id"])
        owner_id = int(app_row["owner_user_id"] or 0)
        approved = int(app_row["is_approved"] or 0)

        if role == "admin" or uid == owner_id:
            return {"app_id": app_id, "owner_user_id": owner_id, "is_approved": approved}

        purchase = db.execute(
            "SELECT 1 FROM purchases WHERE app_id=? AND user_id=? LIMIT 1",
            (app_id, uid),
        ).fetchone()
        if not purchase:
            raise HTTPException(403, "Purchase required")

    return {"app_id": app_id, "owner_user_id": owner_id, "is_approved": approved}


# ===============================
# Developer API
# ===============================

def _require_app_owner_by_slug(slug: str, user_id: int) -> dict:
    with get_db() as db:
        row = db.execute(
            "SELECT id, owner_user_id FROM apps WHERE slug=?",
            (slug,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "App not found")
    if int(row["owner_user_id"]) != int(user_id):
        raise HTTPException(403, "Not your app")
    return dict(row)


def _require_app_owner_by_id(app_id: int, user_id: int) -> dict:
    with get_db() as db:
        row = db.execute(
            "SELECT id, owner_user_id FROM apps WHERE id=?",
            (int(app_id),),
        ).fetchone()
    if not row:
        raise HTTPException(404, "App not found")
    if int(row["owner_user_id"]) != int(user_id):
        raise HTTPException(403, "Not your app")
    return dict(row)


def _require_build_owner(build_id: int, user_id: int) -> dict:
    with get_db() as db:
        row = db.execute(
            """
            SELECT b.id, b.app_id, a.owner_user_id
            FROM builds b
            JOIN apps a ON a.id=b.app_id
            WHERE b.id=?
            """,
            (int(build_id),),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Build not found")
    if int(row["owner_user_id"]) != int(user_id):
        raise HTTPException(403, "Not your app")
    return dict(row)


# App anlegen
@app.post("/api/dev/apps")
async def create_app(payload: AppCreate, user: dict = Depends(require_dev)):
    _require_safe_slug(payload.slug)
    with get_db() as db:
        try:
            db.execute(
                "INSERT INTO apps(slug,title,owner_user_id,created_at) VALUES(?,?,?,?)",
                (payload.slug, payload.title, user["user_id"], datetime.utcnow().isoformat()),
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "unique" in msg or "constraint" in msg:
                raise HTTPException(409, "slug already exists") from exc
            raise
        db.commit()
        app_id = db.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    return {"id": app_id}


# App-Metadaten aktualisieren (Preis, Beschreibung, Cover, Rabatt)
@app.post("/api/dev/apps/{slug}/meta")
async def update_app_meta(slug: str, payload: AppMetaUpdate, user: dict = Depends(require_dev)):
    _require_safe_slug(slug)
    _require_app_owner_by_slug(slug, user["user_id"])
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
    _require_safe_slug(slug)
    _require_app_owner_by_slug(slug, user["user_id"])
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


@app.post("/api/dev/apps/{slug}/unpublish")
async def unpublish_app(slug: str, user: dict = Depends(require_dev)):
    _require_safe_slug(slug)
    _require_app_owner_by_slug(slug, user["user_id"])
    with get_db() as db:
        row = db.execute("SELECT id FROM apps WHERE slug=?", (slug,)).fetchone()
        if not row:
            raise HTTPException(404, "App not found")
        db.execute("UPDATE apps SET is_approved=0 WHERE slug=?", (slug,))
        db.commit()
    return {"ok": True, "is_approved": 0}


# Build anlegen
@app.post("/api/dev/builds")
async def create_build(payload: BuildCreate, user: dict = Depends(require_dev)):
    _require_safe_comp(payload.version, "version")
    _require_safe_comp(payload.platform, "platform")
    _require_safe_comp(payload.channel, "channel")
    _require_app_owner_by_id(payload.app_id, user["user_id"])
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
    _require_build_owner(build_id, user["user_id"])
    missing = []
    for h in req.hashes:
        _require_sha256(h)
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
    hash = _require_sha256(hash)
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
    _require_safe_slug(manifest.app)
    _require_safe_comp(manifest.version, "version")
    _require_safe_comp(manifest.platform, "platform")
    _require_safe_comp(manifest.channel, "channel")
    _validate_manifest_files(manifest)
    _require_build_owner(build_id, user["user_id"])
    with get_db() as db:
        b = db.execute("SELECT * FROM builds WHERE id=?", (build_id,)).fetchone()
        if not b:
            raise HTTPException(404, "Build not found")
        a = db.execute("SELECT * FROM apps WHERE id=?", (b["app_id"],)).fetchone()
        if not a:
            raise HTTPException(404, "App not found")
        if manifest.app != a["slug"]:
            raise HTTPException(400, "Manifest app mismatch")

    manifest_rel = Path(
        f"apps/{manifest.app}/builds/{manifest.version}/{manifest.platform}/{manifest.channel}/manifest.json"
    )
    manifest_path = _safe_resolve(STORAGE_APPS.parent, manifest_rel)
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
    app_id = int(payload.app_id)
    if app_id <= 0:
        raise HTTPException(400, "Invalid app_id")

    user_id = int(user["user_id"])
    with get_db() as db:
        app_row = db.execute(
            "SELECT id, is_approved, price, sale_percent FROM apps WHERE id=?",
            (app_id,),
        ).fetchone()
        if not app_row:
            raise HTTPException(404, "App not found")
        if int(app_row["is_approved"] or 0) != 1:
            raise HTTPException(400, "App not available")

        existing = db.execute(
            "SELECT id FROM purchases WHERE app_id=? AND user_id=? LIMIT 1",
            (app_id, user_id),
        ).fetchone()
        if existing:
            return {"ok": True, "already_reported": True}

        charged_price = _effective_price(
            float(app_row["price"] or 0.0),
            float(app_row["sale_percent"] or 0.0),
        )
        db.execute(
            """
            INSERT INTO purchases(app_id, user_id, price, purchased_at)
            VALUES(?,?,?,?)
            """,
            (
                app_id,
                user_id,
                charged_price,
                datetime.utcnow().isoformat(),
            ),
        )
        db.commit()
    return {"ok": True, "price": charged_price}


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
    _require_download_access(slug, user)
    data, _ = _load_ready_manifest(slug, platform, channel)
    return JSONResponse(content=data)


# Dateien / Chunks ausliefern
@app.get("/storage/chunks/{hash}")
async def get_chunk(
    hash: str,
    slug: str,
    version: str,
    platform: str,
    channel: str,
    user: dict = Depends(require_user),
):
    hash = _require_sha256(hash)
    _require_download_access(slug, user)
    manifest, _ = _load_ready_manifest(slug, platform, channel, version=version)
    if not _manifest_contains_chunk(manifest, hash):
        raise HTTPException(404, "Chunk not in manifest")
    p = STORAGE_CHUNKS / hash[0:2] / hash[2:4] / hash
    if not p.exists():
        raise HTTPException(404, "Chunk not found")
    return FileResponse(p)


@app.get("/storage/apps/{path:path}")
async def get_storage_file(
    path: str,
    slug: str,
    version: str,
    platform: str,
    channel: str,
    user: dict = Depends(require_user),
):
    _require_download_access(slug, user)
    _, manifest_rel = _load_ready_manifest(slug, platform, channel, version=version)

    req_path = _normalize_manifest_file_path(path)
    try:
        expected_rel = Path(manifest_rel).relative_to("apps").as_posix()
    except ValueError as exc:
        raise HTTPException(500, "Manifest path layout invalid") from exc
    if req_path != expected_rel:
        raise HTTPException(403, "File not allowed")

    p = _safe_resolve(STORAGE_APPS, Path(req_path))
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
    q += " ORDER BY created_at DESC, id DESC"
    with get_db() as db:
        rows = [dict(r) for r in db.execute(q, params).fetchall()]
    return {"items": rows}


@admin.get("/submissions/{sid}/manifest")
def get_submission_manifest(sid: int, user=Depends(require_admin)):
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = _safe_resolve(STORAGE_APPS.parent, Path(s["manifest_url"]))
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


def _verify_manifest_file(f: dict) -> dict:
    import hashlib as _hl

    chunk_ok = True
    for ch in f.get("chunks", []):
        if _hl.sha256(_read_chunk(ch["sha256"])).hexdigest() != ch["sha256"]:
            chunk_ok = False
            break

    file_ok = False
    if chunk_ok and f.get("chunks"):
        fh = _hl.sha256()
        for ch in f["chunks"]:
            fh.update(_read_chunk(ch["sha256"]))
        file_ok = fh.hexdigest() == f.get("sha256")

    return {"chunk_ok": chunk_ok, "file_ok": file_ok, "expected": f.get("sha256")}


@admin.get("/submissions/{sid}/files")
def list_submission_files(sid: int, user=Depends(require_admin)):
    # Liefert die Datei-Liste (aus dem Manifest)
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = _safe_resolve(STORAGE_APPS.parent, Path(s["manifest_url"]))
    m = json.loads(mpath.read_text(encoding="utf-8"))
    files = []
    for f in m.get("files", []):
        chunks = f.get("chunks") or []
        chunk_bytes = sum(ch.get("size", 0) or 0 for ch in chunks)
        files.append(
            {
                **f,
                "chunks": chunks,
                "chunk_count": len(chunks),
                "chunk_bytes": chunk_bytes,
            }
        )
    return {"files": files, "app": m.get("app"), "version": m.get("version")}


@admin.get("/submissions/{sid}/files/download")
def download_submission_file(sid: int, path: str, user=Depends(require_admin)):
    # Baut eine Datei aus den Chunks zusammen und streamt sie
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = _safe_resolve(STORAGE_APPS.parent, Path(s["manifest_url"]))
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
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = _safe_resolve(STORAGE_APPS.parent, Path(s["manifest_url"]))
    m = json.loads(mpath.read_text(encoding="utf-8"))
    f = next((x for x in m.get("files", []) if x.get("path") == path), None)
    if not f:
        raise HTTPException(404, "File not in manifest")
    return _verify_manifest_file(f)


@admin.post("/submissions/{sid}/files/verify-batch")
def verify_submission_files_batch(
    sid: int,
    payload: dict = Body(...),
    user=Depends(require_admin),
):
    paths = payload.get("paths") if isinstance(payload, dict) else None
    if not isinstance(paths, list):
        raise HTTPException(400, "paths list required")

    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = _safe_resolve(STORAGE_APPS.parent, Path(s["manifest_url"]))
    m = json.loads(mpath.read_text(encoding="utf-8"))
    files = {f.get("path"): f for f in m.get("files", []) if f.get("path")}

    results = []
    ok_count = 0
    for path in paths:
        f = files.get(path)
        if not f:
            results.append({"path": path, "error": "not_in_manifest"})
            continue
        try:
            result = _verify_manifest_file(f)
        except HTTPException as exc:
            results.append({"path": path, "error": str(exc.detail)})
            continue
        except Exception:
            results.append({"path": path, "error": "verify_failed"})
            continue
        if result.get("chunk_ok") and result.get("file_ok"):
            ok_count += 1
        results.append({"path": path, **result})

    return {"results": results, "ok_count": ok_count, "total": len(paths)}


@admin.get("/submissions/{sid}/files/zip")
def download_submission_zip(sid: int, user=Depends(require_admin)):
    # 1) Submission + Manifest laden
    with get_db() as db:
        s = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Not found")
    mpath = _safe_resolve(STORAGE_APPS.parent, Path(s["manifest_url"]))
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
