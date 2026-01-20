from __future__ import annotations
from pathlib import Path
from typing import Callable, Dict, Any, List
import os, json, requests, hashlib

API = os.environ.get("DIST_API", "http://127.0.0.1:8000")
from services.env import session_path
SESSION_PATH = session_path()
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB

def _headers(role="dev") -> Dict[str, str]:
    uid, r = 0, role
    token = None
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
        uid = s.get("user_id") or s.get("id") or 0
        r = (s.get("role") or role).lower()
        token = s.get("token")
    except FileNotFoundError:
        pass
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def slugify(s: str) -> str:
    import re
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def chunk_file(fp: Path):
    off = 0
    with fp.open("rb") as f:
        while True:
            b = f.read(CHUNK_SIZE)
            if not b: break
            yield off, b
            off += len(b)

def build_manifest(root: Path, app_slug: str, version: str, platform: str, channel: str) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    total_size = 0

    for fp in root.rglob("*"):
        if fp.is_file():
            size = fp.stat().st_size
            total_size += size
            rel = fp.relative_to(root).as_posix()

            chunks = []
            off = 0
            file_hash = hashlib.sha256()
            with fp.open("rb") as f:
                while True:
                    b = f.read(CHUNK_SIZE)
                    if not b:
                        break
                    file_hash.update(b)
                    chunks.append({"offset": off, "size": len(b), "sha256": sha256_bytes(b)})
                    off += len(b)

            files.append({
                "path": rel,
                "size": size,
                "sha256": file_hash.hexdigest(),
                "chunks": chunks
            })

    return {
        "app": app_slug,
        "version": version,
        "platform": platform,
        "channel": channel,
        "total_size": total_size,
        "files": files,
        # so referenziert dein Manifest die Ortung der Chunks:
        "chunk_base": f"apps/{app_slug}/builds/{version}/{platform}/{channel}/chunks",
        "signature": None
    }


# --- API helpers ---
def _get_my_apps() -> list[dict]:
    r = requests.get(f"{API}/api/dev/my-apps", headers=_headers("dev"))
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []

def _find_app_id(slug: str) -> int | None:
    for app in _get_my_apps():
        if str(app.get("slug")) == slug:
            try:
                return int(app.get("id"))
            except Exception:
                return None
    return None

def _get_public_apps() -> list[dict]:
    r = requests.get(f"{API}/api/public/apps", headers=_headers("dev"))
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []

def _find_app_id_public(slug: str) -> int | None:
    for app in _get_public_apps():
        if str(app.get("slug")) == slug:
            try:
                return int(app.get("id"))
            except Exception:
                return None
    return None

def ensure_app(slug: str, title: str) -> int:
    # Versucht anzulegen; wenn schon da und OWNED, nutze die ID.
    existing = _find_app_id(slug)
    if existing:
        return existing

    try:
        r = requests.post(f"{API}/api/dev/apps", headers=_headers("dev"),
                          json={"slug": slug, "title": title})
        r.raise_for_status()
        return int(r.json()["id"])
    except requests.HTTPError as e:
        # Falls die App bereits existiert (Unique Constraint), erneut nachschlagen
        if e.response is not None and e.response.status_code in (400, 409, 500):
            existing = _find_app_id(slug)
            if existing:
                return existing
            # Slug gehört vermutlich einem anderen Dev/Owner
            raise RuntimeError(f"Slug '{slug}' ist bereits vergeben. Bitte anderen Slug wählen oder Besitzer wechseln.") from e
        raise

def create_build(app_id: int, version: str, platform: str, channel: str) -> int:
    r = requests.post(f"{API}/api/dev/builds", headers=_headers("dev"),
                      json={"app_id": app_id, "version": version, "platform": platform, "channel": channel})
    r.raise_for_status()
    return int(r.json()["id"])

def get_missing(build_id: int, hashes: List[str]) -> List[str]:
    r = requests.post(f"{API}/api/dev/builds/{build_id}/missing-chunks",
                      headers=_headers("dev"), json={"hashes": hashes})
    r.raise_for_status()
    return r.json().get("missing", [])

def upload_chunk(h: str, data: bytes):
    r = requests.post(f"{API}/api/dev/chunk/{h}", data=data,
                      headers={**_headers("dev"), "Content-Type": "application/octet-stream"})
    r.raise_for_status()

def finalize_build(
    build_id: int,
    slug: str,
    version: str,
    platform: str,
    channel: str,
    total_size: int,
    files: list
) -> str:
    url = f"{API}/api/dev/builds/{build_id}/finalize"
    manifest = {
        "app": slug,
        "version": version,
        "platform": platform,
        "channel": channel,
        "total_size": total_size,
        "files": files,
        "chunk_base": f"apps/{slug}/builds/{version}/{platform}/{channel}/chunks",
        "signature": None
    }
    r = requests.post(url, headers=_headers("dev"), json=manifest, timeout=30)
    print("Finalize response:", r.status_code, r.text)
    r.raise_for_status()
    return r.json().get("manifest_url", "")

def upload_folder(title: str, slug: str, version: str, platform: str, channel: str,
                  folder: Path,
                  on_progress: Callable[[int], None] | None = None,
                  on_log: Callable[[str], None] | None = None) -> str:
    if on_log: on_log("Manifest wird erstellt…")
    manifest = build_manifest(folder, slug, version, platform, channel)
    app_id = ensure_app(slug, title)
    if on_log: on_log(f"App angelegt/gefunden: slug={slug}")

    if on_log: on_log("Build wird angelegt…")
    build_id = create_build(app_id, version, platform, channel)
    if on_log: on_log(f"Build-ID: {build_id}")

    # fehlende Chunks
    all_hashes = []
    for f in manifest["files"]:
        for c in f["chunks"]:
            all_hashes.append(c["sha256"])
    if on_log: on_log(f"{len(all_hashes)} Chunks prüfen…")
    missing = set(get_missing(build_id, all_hashes))
    if on_log: on_log(f"{len(missing)} Chunks fehlen – Upload startet")

    # Upload
    uploaded = 0
    total_to_upload = len(missing) if missing else 1
    for fp in folder.rglob("*"):
        if not fp.is_file(): continue
        for _, b in chunk_file(fp):
            h = sha256_bytes(b)
            if h in missing:
                upload_chunk(h, b)
                uploaded += 1
                if on_progress:
                    on_progress(int(uploaded * 100 / total_to_upload))
    if on_log: on_log("Finalize…")
    manifest_url = finalize_build(
        build_id=build_id,
        slug=manifest["app"],
        version=manifest["version"],
        platform=manifest["platform"],
        channel=manifest["channel"],
        total_size=manifest["total_size"],
        files=manifest["files"]
    )
    if on_log: on_log(f"Fertig. Manifest: {manifest_url or '(keine URL erhalten)'}")
    if on_progress: on_progress(100)
    return manifest_url

def set_app_meta(
    slug: str,
    price: float,
    description: str | None,
    cover: str | None,
    title: str | None = None,
    role: str = "dev",
) -> dict:
    """Setzt Titel, Preis, Beschreibung & Cover (URL oder Datei) für ein Spiel."""
    payload = {
        "price": float(price),
        "description": description or None,
        "cover_url": None,
    }
    if title:
        payload["title"] = title
    is_url = False
    if cover:
        is_url = cover.startswith("http://") or cover.startswith("https://")
        if is_url:
            payload["cover_url"] = cover
    r = requests.post(f"{API}/api/dev/apps/{slug}/meta", headers=_headers(role), json=payload)
    r.raise_for_status()
    if cover and not is_url:
        with open(cover, "rb") as f:
            files = {"file": (Path(cover).name, f, "application/octet-stream")}
            rc = requests.post(f"{API}/api/dev/apps/{slug}/cover", headers=_headers(role), files=files)
            rc.raise_for_status()
            return rc.json()
    return r.json()
