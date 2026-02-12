import os
import json
import sys
import shutil
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8000"

def data_root() -> Path:
    root = Path.home() / ".indie-hain"
    root.mkdir(parents=True, exist_ok=True)
    return root

def _settings_value(keys: tuple[str, ...]) -> str | None:
    for candidate in _settings_paths():
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            for key in keys:
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val
    return None

def _settings_list(keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for candidate in _settings_paths():
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for key in keys:
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    values.append(val.strip())
                elif isinstance(val, list):
                    for entry in val:
                        if isinstance(entry, str) and entry.strip():
                            values.append(entry.strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered

def migration_block_path() -> Path:
    return data_root() / ".skip_legacy_migration"

def legacy_db_paths() -> list[Path]:
    candidates: list[Path] = [
        Path.cwd() / "data" / "indiehain.db",
    ]
    base_dir = Path(__file__).resolve().parents[1]
    candidates.append(base_dir / "data" / "indiehain.db")
    exe = Path(sys.executable).resolve()
    candidates.append(exe.parent / "data" / "indiehain.db")
    for parent in exe.parents:
        if parent.suffix == ".app":
            candidates.extend([
                parent.parent / "data" / "indiehain.db",
                parent / "Contents" / "Resources" / "data" / "indiehain.db",
            ])
            break
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered

def ensure_legacy_db_migrated() -> bool:
    if migration_block_path().exists():
        return False
    target = data_root() / "indiehain.db"
    if target.exists():
        return False
    for legacy in legacy_db_paths():
        if legacy.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy, target)
                return True
            except Exception:
                return False
    return False

def session_path() -> Path:
    return data_root() / "session.json"

def _settings_api() -> str | None:
    return _settings_value(("DIST_API", "dist_api"))

def _settings_install_dir() -> str | None:
    return _settings_value(("INSTALL_DIR", "install_dir", "INDIE_HAIN_INSTALL_DIR", "indie_hain_install_dir"))

def _settings_legacy_install_dirs() -> list[str]:
    return _settings_list(("LEGACY_INSTALL_DIRS", "legacy_install_dirs", "legacy_install_dir"))

def legacy_install_dir_settings() -> list[str]:
    return _settings_legacy_install_dirs()

def missing_legacy_install_dirs() -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for entry in _settings_legacy_install_dirs():
        if not isinstance(entry, str):
            continue
        raw = entry.strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = data_root() / path
        try:
            exists = path.resolve().exists()
        except Exception:
            exists = path.exists()
        if not exists:
            missing.append(raw)
    return missing

def _resolve_install_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = data_root() / path
    return path

def _settings_paths() -> list[Path]:
    candidates: list[Path] = [
        data_root() / "indie-hain.json",
        data_root() / "settings.json",
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

def settings_write_path() -> Path:
    path = data_root() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}

def update_settings(values: dict[str, object | None]) -> None:
    path = settings_write_path()
    data = _load_settings(path)
    for key, value in values.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

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

def install_root() -> Path:
    env_val = os.environ.get("INDIE_HAIN_INSTALL_DIR") or os.environ.get("INSTALL_DIR")
    setting_val = _settings_install_dir()
    raw = env_val or setting_val
    if raw:
        root = _resolve_install_dir(raw)
    else:
        root = data_root() / "Installed"
    root.mkdir(parents=True, exist_ok=True)
    return root

def legacy_install_roots() -> list[Path]:
    candidates: list[Path] = [
        Path.cwd() / "Installed",
    ]
    for path in _settings_legacy_install_dirs():
        candidates.append(_resolve_install_dir(path))
    base_dir = Path(__file__).resolve().parents[1]
    candidates.append(base_dir / "Installed")
    exe = Path(sys.executable).resolve()
    candidates.append(exe.parent / "Installed")
    for parent in exe.parents:
        if parent.suffix == ".app":
            candidates.extend([
                parent.parent / "Installed",
                parent / "Contents" / "Resources" / "Installed",
            ])
            break
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered

def add_legacy_install_dir(path: Path) -> None:
    raw = str(path.expanduser())
    if not raw.strip():
        return
    settings_path = settings_write_path()
    data = _load_settings(settings_path)
    legacy = data.get("legacy_install_dirs")
    if not isinstance(legacy, list):
        legacy = []
    if raw not in legacy:
        legacy.append(raw)
    update_settings({"legacy_install_dirs": legacy})

def _normalize_legacy_value(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = data_root() / path
    try:
        return str(path.resolve())
    except Exception:
        return str(path)

def remove_legacy_install_dir(path: str | Path) -> bool:
    raw = str(path) if isinstance(path, Path) else path
    raw = raw.strip()
    if not raw:
        return False
    settings_path = settings_write_path()
    data = _load_settings(settings_path)
    legacy = data.get("legacy_install_dirs")
    if not isinstance(legacy, list):
        return False
    target_normalized = _normalize_legacy_value(raw)
    filtered: list[str] = []
    removed = False
    for entry in legacy:
        if not isinstance(entry, str):
            continue
        entry_raw = entry.strip()
        entry_normalized = _normalize_legacy_value(entry_raw)
        if entry_raw == raw or entry_normalized == target_normalized:
            removed = True
            continue
        filtered.append(entry_raw)
    if removed:
        update_settings({"legacy_install_dirs": filtered})
    return removed

def clear_legacy_install_dirs() -> None:
    update_settings({"legacy_install_dirs": []})

def abs_url(u: str) -> str:
    if not u: return ""
    return u if u.startswith("http") else f"{api_base()}{u}"


def launcher_theme() -> str:
    raw = _settings_value(("LAUNCHER_THEME", "launcher_theme"))
    theme = (raw or "").strip().lower()
    if theme in {"light", "dark"}:
        return theme
    return "dark"


def set_launcher_theme(theme: str) -> None:
    normalized = str(theme or "").strip().lower()
    if normalized not in {"light", "dark"}:
        normalized = "dark"
    update_settings({"launcher_theme": normalized})
