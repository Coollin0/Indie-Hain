# distribution_client/downloader.py
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, hashlib

from services.env import api_base

API = api_base()  # Distribution-Backend (FastAPI)
MANIFEST_TIMEOUT = 20
CHUNK_TIMEOUT = 120

def _headers(role="user"):
    from data import store
    return store.auth_headers()

def get_manifest(slug: str, platform: str = "windows", channel: str = "stable") -> dict:
    r = requests.get(
        f"{API}/api/manifest/{slug}/{platform}/{channel}",
        headers=_headers("user"),
        timeout=MANIFEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()

def _download_chunk(h: str, slug: str, version: str, platform: str, channel: str) -> bytes:
    r = requests.get(
        f"{API}/storage/chunks/{h}",
        headers=_headers("user"),
        params={
            "slug": slug,
            "version": version,
            "platform": platform,
            "channel": channel,
        },
        timeout=CHUNK_TIMEOUT,
    )
    r.raise_for_status()
    data = r.content
    if hashlib.sha256(data).hexdigest() != h:
        raise RuntimeError(f"Chunk hash mismatch: {h}")
    return data


def _safe_output_path(base: Path, rel_path: str) -> Path:
    raw = (rel_path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise RuntimeError(f"Invalid path in manifest: {rel_path!r}")
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise RuntimeError(f"Invalid path in manifest: {rel_path!r}")

    target = (base / Path(*parts)).resolve()
    base_resolved = base.resolve()
    if not target.is_relative_to(base_resolved):
        raise RuntimeError(f"Path escapes install root: {rel_path!r}")
    return target

def install_from_manifest(man: dict, install_dir: Path, workers: int = 6):
    install_dir.mkdir(parents=True, exist_ok=True)
    slug = str(man.get("app") or "")
    version = str(man.get("version") or "")
    platform = str(man.get("platform") or "windows")
    channel = str(man.get("channel") or "stable")
    if not slug:
        raise RuntimeError("Manifest app slug missing")
    if not version:
        raise RuntimeError("Manifest version missing")

    # 1) Chunks parallel laden
    chunk_hashes = [c["sha256"] for f in man["files"] for c in f["chunks"]]
    data_map = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_download_chunk, h, slug, version, platform, channel): h
            for h in chunk_hashes
        }
        for fut in as_completed(futs):
            h = futs[fut]
            data_map[h] = fut.result()

    # 2) Dateien zusammensetzen + Hash prüfen
    for f in man["files"]:
        out = _safe_output_path(install_dir, str(f["path"]))
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as dst:
            for c in f["chunks"]:
                dst.write(data_map[c["sha256"]])
        with out.open("rb") as check:
            if hashlib.sha256(check.read()).hexdigest() != f["sha256"]:
                raise RuntimeError(f"Hash mismatch for {f['path']}")
    return True
