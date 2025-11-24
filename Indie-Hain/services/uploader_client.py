from __future__ import annotations
from pathlib import Path
from typing import Callable, Dict, Any, List
import os, json, requests, hashlib

API = os.environ.get("DIST_API", "http://127.0.0.1:8000")
SESSION_PATH = os.path.join("data", "session.json")
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB

def _headers(role="dev") -> Dict[str, str]:
    user_id = 0
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            user_id = json.load(f).get("user_id", 0)
    except FileNotFoundError:
        pass
    # MVP-Auth per Header (Option B/JWT kannst du später tauschen)
    return {"X-User-Id": str(user_id or 0), "X-Role": role}

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
    total = 0
    for fp in root.rglob("*"):
        if fp.is_file():
            size = fp.stat().st_size
            total += size
            rel = fp.relative_to(root).as_posix()
            chunks = []
            file_bytes = bytearray()
            for _, b in chunk_file(fp):
                h = sha256_bytes(b)
                file_bytes.extend(b)
                chunks.append({"sha256": h, "size": len(b)})
            fhash = hashlib.sha256(file_bytes).hexdigest()
            files.append({"path": rel, "size": size, "sha256": fhash, "chunks": chunks})
    return {
        "app": app_slug,
        "version": version,
        "platform": platform,
        "channel": channel,
        "files": files,
        "chunk_base": "/storage/chunks"
    }

# --- API helpers ---
def ensure_app(slug: str, title: str) -> int:
    # versucht anzulegen; wenn schon da, ignorieren und ID nachschlagen
    try:
        r = requests.post(f"{API}/api/dev/apps", headers=_headers("dev"),
                          json={"slug": slug, "title": title})
        r.raise_for_status()
        return int(r.json()["id"])
    except requests.HTTPError:
        # Nachschlagen via (kleiner Trick): leg direkt den Build an – falls App fehlt, crasht’s
        # Besser: kleiner GET-Helper im Backend – fürs MVP lesen wir aus der Fehlermeldung nicht.
        # Workaround: Fake-Query: wir versuchen Build-Insert mit app_id 0 -> 404
        # Stattdessen: Dev trägt die app_id nicht ein – darum: wir lassen es ohne ID und vertrauen auf slug später.
        return -1

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

def finalize_build(build_id: int, manifest: Dict[str, Any]) -> str:
    r = requests.post(f"{API}/api/dev/builds/{build_id}/finalize",
                      headers=_headers("dev"), json=manifest)
    r.raise_for_status()
    return r.json()["manifest_url"]

def upload_folder(title: str, slug: str, version: str, platform: str, channel: str,
                  folder: Path,
                  on_progress: Callable[[int], None] | None = None,
                  on_log: Callable[[str], None] | None = None) -> str:
    if on_log: on_log("Manifest wird erstellt…")
    manifest = build_manifest(folder, slug, version, platform, channel)
    app_id = ensure_app(slug, title)
    if on_log: on_log(f"App angelegt/gefunden: slug={slug}")

    if on_log: on_log("Build wird angelegt…")
    build_id = create_build(app_id if app_id > 0 else 1, version, platform, channel)  # MVP: app_id 1, wenn nicht bekannt
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
    url = finalize_build(build_id, manifest)
    if on_log: on_log(f"Fertig. Manifest: {url}")
    if on_progress: on_progress(100)
    return url
