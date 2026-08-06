"""Generación de la huella de la PC (machine id) para atar licencias Pro.

La licencia Pro se firma con un campo `machine` que contiene esta huella, de
modo que una misma clave sólo es válida en la computadora para la que se
emitió.  Si el usuario formatea Windows (o cambia la placa), la huella cambia
y la licencia deja de validar — por eso la licencia es "por dispositivo".

Sensores combinados (hash SHA-256 → 16 hex):
  - MachineGuid del registry de Windows (estable por instalación de Windows)
  - Serial de volumen de la unidad del SO (estable por disco)
  - MAC primaria (uuid.getnode)

Sólo se expone el *hash*: no se filtran datos crudos (ni MAC ni nombres).
"""
import ctypes
import hashlib
import platform
import sys
import uuid

_IS_WINDOWS = sys.platform.startswith("win")


def _win_machine_guid() -> str:
    if not _IS_WINDOWS:
        return ""
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
        return str(val)
    except Exception:
        return ""


def _volume_serial(drive: str = "C:\\") -> str:
    if not _IS_WINDOWS:
        return ""
    try:
        serial = ctypes.c_ulong(0)
        label = ctypes.create_unicode_buffer(256)
        fs = ctypes.create_unicode_buffer(64)
        flags = ctypes.c_ulong(0)
        total = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetVolumeInformationW(
            drive, label, ctypes.sizeof(label),
            ctypes.byref(serial), ctypes.byref(total),
            ctypes.byref(flags), fs, ctypes.sizeof(fs)
        )
        return "%08X" % serial.value
    except Exception:
        return ""


def _mac_address() -> str:
    try:
        node = uuid.getnode()
        if node in (0, None):
            return ""
        return "%012X" % node
    except Exception:
        return ""


def _sensors() -> list[str]:
    out = []
    gu = _win_machine_guid()
    if gu:
        out.append("G:" + gu)
    vs = _volume_serial()
    if vs:
        out.append("V:" + vs)
    mac = _mac_address()
    if mac:
        out.append("M:" + mac)
    # fallback estable por plataforma (para equipos donde falla todo arriba)
    out.append("P:" + platform.platform() + "|" + platform.node())
    return out


def machine_id() -> str:
    """Huella de la PC: hash de 16 hex caracteres."""
    raw = "|".join(_sensors())
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]


def machine_display() -> str:
    """Id corto para que el usuario lo copie y envíe por email (16 hex)."""
    return machine_id()
