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
import re
import subprocess
import sys
import uuid

_IS_WINDOWS = sys.platform.startswith("win")

# Valores genéricos/no-válidos que devuelven VMs o placas sin UUID real
_INVALID_UUIDS = {
    "03000200-0400-0500-0006-000700080009",
    "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
    "00000000-0000-0000-0000-000000000000",
}


def _is_bad_uuid(val: str) -> bool:
    """True si un UUID candidato es genérico, mal formado o informativo."""
    v = val.strip().upper().replace("-", "")
    if len(v) != 32 or not all(c in "0123456789ABCDEF" for c in v):
        return True
    canon = f"{v[0:8]}-{v[8:12]}-{v[12:16]}-{v[16:20]}-{v[20:32]}".upper()
    if canon.replace("-", "") in {x.replace("-", "") for x in _INVALID_UUIDS}:
        return True
    if canon in {"DEFAULT STRING", "NOT PRESENT", "NONE", "N/A", "NOT AVAILABLE"}:
        return True
    return False


def _normalize_uuid(val: str) -> str:
    """Normaliza un UUID al formato 8-4-4-4-12 en mayúsculas."""
    v = val.strip().upper().replace("-", "")
    if len(v) != 32:
        return ""
    return f"{v[0:8]}-{v[8:12]}-{v[12:16]}-{v[16:20]}-{v[20:32]}"


def _smbios_uuid() -> str:
    """UUID de la placa madre via WMI (Win32_ComputerSystemProduct).
    Sobrevive a reinstalaciones de Windows en el mismo hardware.
    """
    if not _IS_WINDOWS:
        return ""
    # Intento 1: PowerShell (más confiable y rápido)
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        val = (r.stdout or "").strip()
        if val and not _is_bad_uuid(val):
            return _normalize_uuid(val)
    except Exception:
        pass
    # Intento 2: wmic (fallback para sistemas viejos)
    try:
        r = subprocess.run(
            ["wmic", "path", "Win32_ComputerSystemProduct", "get", "UUID"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line and line.upper() != "UUID" and not _is_bad_uuid(line):
                norm = _normalize_uuid(line)
                if norm:
                    return norm
    except Exception:
        pass
    return ""


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
    # Ancla primaria: SMBIOS UUID (sobrevive a reinstalar Windows en misma HW)
    sm = _smbios_uuid()
    if sm:
        out.append("S:" + sm)
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


def _sensors_legacy() -> list[str]:
    """Sensores sin SMBIOS, para compatibilidad con licencias ya emitidas."""
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
    out.append("P:" + platform.platform() + "|" + platform.node())
    return out


def machine_id_legacy() -> str:
    """Huella legacy (sin SMBIOS) para compatibilidad con claves ya emitidas."""
    raw = "|".join(_sensors_legacy())
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]


def machine_id() -> str:
    """Huella de la PC: hash de 16 hex caracteres."""
    raw = "|".join(_sensors())
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]


def machine_display() -> str:
    """Id corto para que el usuario lo copie y envíe por email (16 hex)."""
    return machine_id()
