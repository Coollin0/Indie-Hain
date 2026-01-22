from pathlib import Path
import hashlib, json, requests, sys, os

CHUNK_SIZE = 8 * 1024 * 1024

API = "http://127.0.0.1:8000"
ACCESS_TOKEN = os.environ.get("INDIE_HAIN_ACCESS_TOKEN")
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"} if ACCESS_TOKEN else {}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def chunk_file(fp: Path):
    off = 0
    with fp.open("rb") as f:
        while True:
            b = f.read(CHUNK_SIZE)
            if not b:
                break
            yield off, b
            off += len(b)


def build_manifest(root: Path, app_slug: str, version: str, platform: str, channel: str):
    files = []
    total = 0
    for fp in root.rglob("*"):
        if fp.is_file():
            size = fp.stat().st_size
            total += size
            chunks = []
            h_file = hashlib.sha256()
            for off, b in chunk_file(fp):
                h_file.update(b)
                chunks.append({
                    "offset": off,
                    "size": len(b),
                    "sha256": sha256_bytes(b)
                })
            files.append({
                "path": str(fp.relative_to(root)).replace("\\", "/"),
                "size": size,
                "sha256": h_file.hexdigest(),
                "chunks": chunks
            })
    return {
        "app": app_slug,
        "version": version,
        "platform": platform,
        "channel": channel,
        "total_size": total,
        "files": files,
        "chunk_base": f"{API}/storage/chunks/" # MVP: API leitet nicht; später CDN
    }


def collect_all_chunk_hashes(manifest: dict):
    s = set()
    for f in manifest["files"]:
        for c in f["chunks"]:
            s.add(c["sha256"])
    return list(s)


def ensure_build(app_id: int, version: str, platform: str, channel: str) -> int:
    r = requests.post(f"{API}/api/dev/builds", json={
        "app_id": app_id, "version": version, "platform": platform, "channel": channel
    }, headers=HEADERS)
    r.raise_for_status()
    return r.json()["id"]


def main():
    if len(sys.argv) < 6:
        print("Usage: python dev_uploader.py <app_id> <app_slug> <version> <platform> <folder> [channel]")
        sys.exit(1)
    app_id = int(sys.argv[1])
    app_slug = sys.argv[2]
    version = sys.argv[3]
    platform = sys.argv[4]
    folder = Path(sys.argv[5]).resolve()
    channel = sys.argv[6] if len(sys.argv) > 6 else "stable"

    build_id = ensure_build(app_id, version, platform, channel)
    manifest = build_manifest(folder, app_slug, version, platform, channel)

    # Fehlende Chunks abfragen
    hashes = collect_all_chunk_hashes(manifest)
    r = requests.post(f"{API}/api/dev/builds/{build_id}/missing-chunks", json={"hashes": hashes}, headers=HEADERS)
    r.raise_for_status()
    missing = set(r.json()["missing"])

    # Fehlende Chunks hochladen
    for f in manifest["files"]:
        for c in f["chunks"]:
            h = c["sha256"]
            if h in missing:
                # Chunkdaten erneut lesen
                fp = folder / f["path"]
                with fp.open("rb") as src:
                    src.seek(c["offset"])
                    data = src.read(c["size"])
                ru = requests.post(
                    f"{API}/api/dev/chunk/{h}",
                    data=data,
                    headers={**HEADERS, "Content-Type": "application/octet-stream"},
                )
                ru.raise_for_status()

    # Finalisieren
    r = requests.post(f"{API}/api/dev/builds/{build_id}/finalize", json=manifest, headers=HEADERS)
    r.raise_for_status()
    print("Manifest URL:", r.json()["manifest_url"])

if __name__ == "__main__":
    main()
