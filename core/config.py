import json
import os
import importlib.util
from pathlib import Path

APP_NAME = "FileCopier"


def config_dir() -> Path:
    """Directorio de configuración del usuario: %APPDATA%\\FileCopier
    (fallback: ~/.config/FileCopier en sistemas sin APPDATA)."""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def ensure_config_dir() -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def filters_config_path() -> Path:
    return config_dir() / "filters_config.json"


def license_config_path() -> Path:
    return config_dir() / "app_config.json"


def log_path() -> Path:
    return config_dir() / "fileCopier_log.txt"


def _read_json(path: Path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: Path, data):
    try:
        ensure_config_dir()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ─── Licencia / edición ──────────────────────────────────────

def _pro_supported() -> bool:
    """La edición pública (open source, gratis) se genera SIN el módulo
    licensing/ y con core/public_edition.py marcado: en ese caso la activación
    Pro no existe y is_pro() es False."""
    try:
        from . import public_edition as _pe
        if getattr(_pe, "FREE_BUILD", False):
            return False
    except ImportError:
        pass
    return importlib.util.find_spec("licensing") is not None


def _machine_match(data: dict) -> bool:
    """True si la licencia está atada a esta PC (o no lleva binding).
    Prueba el formato actual (con SMBIOS) y el legacy (sin SMBIOS) para
    mantener compatibilidad con claves ya emitidas antes de esta mejora."""
    expected = data.get("machine", "")
    if not expected:
        return True  # licencia legacy sin binding: sigue válida
    try:
        from core.machine import machine_id, machine_id_legacy
        if expected == machine_id():
            return True
        if expected == machine_id_legacy():
            return True
        return False
    except Exception:
        return True  # si no se puede calcular la huella, no bloqueamos


def get_license_state() -> dict:
    if not _pro_supported():
        return {"pro": False, "edition": "free"}
    data = _read_json(license_config_path(), {})
    if not isinstance(data, dict):
        data = {}
    # Si la licencia está atada a otra PC, se comporta como no activada.
    if not _machine_match(data):
        data = {"pro": False, "edition": "free", "machine_mismatch": True}
    else:
        data["edition"] = "pro" if data.get("pro") else "free"
    return data


def is_pro() -> bool:
    if not _pro_supported():
        return False
    data = _read_json(license_config_path(), {})
    if not isinstance(data, dict):
        return False
    if not (data.get("pro") and data.get("key")):
        return False
    return _machine_match(data)


def set_license(pro: bool, key: str = "", name: str = "", email: str = "",
                 machine: str = "", expires: str = ""):
    data = _read_json(license_config_path(), {})
    if not isinstance(data, dict):
        data = {}
    data["pro"] = pro
    data["key"] = key
    data["name"] = name
    data["email"] = email
    data["machine"] = machine
    data["expires"] = expires
    _write_json(license_config_path(), data)


def clear_license():
    try:
        license_config_path().unlink(missing_ok=True)
    except Exception:
        pass


def migrate_legacy_config():
    """Copia una sola vez el filters_config.json viejo (raíz del proyecto)
    hacia el directorio de configuración persistente."""
    target = filters_config_path()
    if target.exists():
        return
    legacy = Path(__file__).resolve().parent.parent / "filters_config.json"
    if legacy.exists():
        try:
            ensure_config_dir()
            legacy.replace(target)
        except Exception:
            pass
