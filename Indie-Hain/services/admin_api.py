# services/admin_api.py
import requests
from services.env import api_base

API = api_base()

def _hdrs():
    from data import store
    return store.auth_headers()

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


def grant_dev_upgrade(user_id: int, note: str | None = None):
    payload = {"note": note} if note else {}
    r = requests.post(
        f"{API}/api/admin/users/{int(user_id)}/dev-upgrade/grant",
        headers=_hdrs(),
        json=payload,
    )
    r.raise_for_status()
    return r.json().get("user")
