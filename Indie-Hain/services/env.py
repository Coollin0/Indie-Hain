import os
import json
import sys
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8000"

def session_path() -> Path:
    root = Path.home() / ".indie-hain"
    root.mkdir(parents=True, exist_ok=True)
    return root / "session.json"

def _settings_api() -> str | None:
    for candidate in _settings_paths():
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

def _settings_paths() -> list[Path]:
    candidates: list[Path] = [
        Path.cwd() / "indie-hain.json",
        Path.cwd() / "settings.json",
    ]
    exe = Path(sys.executable).resolve()
    candidates.extend([
        exe.parent / "indie-hain.json",
        exe.parent / "settings.json",
    ])
    for parent in exe.parents:
        if parent.suffix == ".app":
            candidates.extend([
                parent.parent / "indie-hain.json",
                parent.parent / "settings.json",
                parent / "Contents" / "Resources" / "indie-hain.json",
                parent / "Contents" / "Resources" / "settings.json",
            ])
            break
    return candidates

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
