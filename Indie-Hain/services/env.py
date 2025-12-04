import os
def api_base() -> str:
    return os.environ.get("DIST_API", "http://127.0.0.1:8000").rstrip("/")
def abs_url(u: str) -> str:
    if not u: return ""
    return u if u.startswith("http") else f"{api_base()}{u}"
