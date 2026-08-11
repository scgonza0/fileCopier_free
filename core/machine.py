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
import os
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path

_IS_WINDOWS = sys.platform.startswith("win")
_IS_MACOS = sys.platform.startswith("darwin")
_IS_LINUX = sys.platform.startswith("linux")

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


# ── Sensores multiplataforma (macOS / Linux) ───────────────────────

def _macos_hw_uuid() -> str:
    """UUID de hardware Apple (IOPlatformUUID). Sobrevive a reinstalar macOS."""
    if not _IS_MACOS:
        return ""
    for cmd in [
        ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
        ["system_profiler", "SPHardwareDataType"],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            m = re.search(r'"?IOPlatformUUID"?\s*=\s*"([^"]+)"', r.stdout)
            if not m:
                m = re.search(r"Hardware UUID:\s*(\S+)", r.stdout)
            if m:
                val = m.group(1).strip()
                if val and len(val) >= 16:
                    return val.upper()
        except Exception:
            continue
    return ""


def _linux_hw_uuid() -> str:
    """UUID de hardware/producto en Linux. Estable por instalación."""
    if not _IS_LINUX:
        return ""
    # 1) product_uuid de DMI (más estable; a veces requiere root)
    for path in ["/sys/class/dmi/id/product_uuid",
                 "/etc/machine-id",
                 "/var/lib/dbus/machine-id"]:
        try:
            val = Path(path).read_text().strip()
            if val and len(val) >= 16:
                return val.upper()
        except Exception:
            continue
    # 2) dbus-uuidgen como último recurso
    try:
        r = subprocess.run(["dbus-uuidgen"], capture_output=True, text=True, timeout=4)
        val = r.stdout.strip()
        if val:
            return val.upper()
    except Exception:
        pass
    return ""


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
    if _IS_MACOS:
        return _sensors_macos()
    if _IS_LINUX:
        return _sensors_linux()
    # ── Windows: comportamiento IDÉNTICO a v1.0.2 (sin cambios) ──────
    out = []
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
    out.append("P:" + platform.platform() + "|" + platform.node())
    return out


def _sensors_macos() -> list[str]:
    """Sensores para macOS: IOPlatformUUID como ancla primaria."""
    out = []
    mu = _macos_hw_uuid()
    if mu:
        out.append("U:" + mu)
    mac = _mac_address()
    if mac:
        out.append("M:" + mac)
    out.append("P:" + platform.platform() + "|" + platform.node())
    return out


def _sensors_linux() -> list[str]:
    """Sensores para Linux: product_uuid / machine-id como ancla primaria."""
    out = []
    lu = _linux_hw_uuid()
    if lu:
        out.append("U:" + lu)
    mac = _mac_address()
    if mac:
        out.append("M:" + mac)
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
