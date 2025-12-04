# services/admin_api.py
import os, requests
API = os.environ.get("DIST_API", "http://127.0.0.1:8000")

def _hdrs():
    from data import store
    user = getattr(store, "session", None) and store.session.current_user
    user_id = getattr(user, "id", 0) if user else 0
    return {"X-User-Id": str(user_id), "X-Role": "admin"}

def list_submissions(status=None):
    params = {"status": status} if status else None
    r = requests.get(f"{API}/api/admin/submissions", headers=_hdrs(), params=params)
    r.raise_for_status()
    return r.json()["items"]

def get_manifest(sid: int):
    r = requests.get(f"{API}/api/admin/submissions/{sid}/manifest", headers=_hdrs())
    r.raise_for_status()
    return r.json()

def approve_submission(sid: int):
    r = requests.post(f"{API}/api/admin/submissions/{sid}/approve", headers=_hdrs())
    r.raise_for_status()
    return True

def reject_submission(sid: int, note: str | None = None):
    r = requests.post(f"{API}/api/admin/submissions/{sid}/reject", headers=_hdrs(), json={"note": note})
    r.raise_for_status()
    return True

def _hdrs():
    from data import store
    u = getattr(store, "session", None) and store.session.current_user
    uid = getattr(u, "id", 0) if u else 0
    return {"X-User-Id": str(uid), "X-Role": "admin"}

def list_files(sid: int):
    r = requests.get(f"{API}/api/admin/submissions/{sid}/files", headers=_hdrs())
    r.raise_for_status()
    return r.json()

def verify_file(sid: int, path: str):
    r = requests.post(f"{API}/api/admin/submissions/{sid}/files/verify",
                      headers=_hdrs(), params={"path": path})
    r.raise_for_status()
    return r.json()

def file_download_url(sid: int, path: str) -> str:
    # Direktlink, den wir im Browser/OS öffnen
    import urllib.parse as up
    return f'{API}/api/admin/submissions/{sid}/files/download?path={up.quote(path)}'

def zip_download_url(sid: int) -> str:
    return f"{API}/api/admin/submissions/{sid}/files/zip"
