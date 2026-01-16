import os
import json
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8000"

def _settings_api() -> str | None:
    for candidate in (Path.cwd() / "indie-hain.json", Path.cwd() / "settings.json"):
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            for key in ("DIST_API", "dist_api"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val
    return None

def api_base() -> str:
    env_val = os.environ.get("DIST_API")
    if env_val:
        return env_val.rstrip("/")
    settings_val = _settings_api()
    if settings_val:
        return settings_val.rstrip("/")
    try:
        import config
        cfg_val = getattr(config, "DIST_API", "")
        if isinstance(cfg_val, str) and cfg_val.strip():
            return cfg_val.rstrip("/")
    except Exception:
        pass
    return DEFAULT_API
def abs_url(u: str) -> str:
    if not u: return ""
    return u if u.startswith("http") else f"{api_base()}{u}"
