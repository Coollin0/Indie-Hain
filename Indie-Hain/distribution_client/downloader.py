# distribution_client/downloader.py
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, json, os, hashlib

from services.env import api_base

API = api_base()  # Distribution-Backend (FastAPI)
SESSION_PATH = os.path.join("data", "session.json")

def _headers(role="user"):
    user_id = 0
    token = None
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            user_id = data.get("user_id", 0)
            token = data.get("token")
    except FileNotFoundError:
        pass
    headers = {"X-User-Id": str(user_id or 0), "X-Role": role}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def get_manifest(slug: str, platform: str = "windows", channel: str = "stable") -> dict:
    r = requests.get(f"{API}/api/manifest/{slug}/{platform}/{channel}", headers=_headers("user"))
    r.raise_for_status()
    return r.json()

def _download_chunk(h: str) -> bytes:
    r = requests.get(f"{API}/storage/chunks/{h}", headers=_headers("user"))
    r.raise_for_status()
    return r.content

def install_from_manifest(man: dict, install_dir: Path, workers: int = 6):
    install_dir.mkdir(parents=True, exist_ok=True)

    # 1) Chunks parallel laden
    chunk_hashes = [c["sha256"] for f in man["files"] for c in f["chunks"]]
    data_map = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_download_chunk, h): h for h in chunk_hashes}
        for fut in as_completed(futs):
            h = futs[fut]
            data_map[h] = fut.result()

    # 2) Dateien zusammensetzen + Hash prüfen
    for f in man["files"]:
        out = install_dir / f["path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as dst:
            for c in f["chunks"]:
                dst.write(data_map[c["sha256"]])
        with out.open("rb") as check:
            if hashlib.sha256(check.read()).hexdigest() != f["sha256"]:
                raise RuntimeError(f"Hash mismatch for {f['path']}")
    return True
