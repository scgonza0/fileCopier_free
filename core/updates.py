"""Chequeo de actualizaciones usando la API pública de GitHub Releases.
No requiere servidor propio: solo un repo público con releases taggeadas.

Ejemplo: GITHUB_REPO = "tucuenta/fileCopier"
  → https://api.github.com/repos/tucuenta/fileCopier/releases/latest
"""
import json
import urllib.request

from .version import APP_VERSION, GITHUB_REPO


def latest_release() -> dict:
    """Devuelve {'tag': ..., 'url': ...} de la última release, o None."""
    if not GITHUB_REPO:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "FileCopier"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    return {
        "tag": str(data.get("tag_name", "")),
        "url": str(data.get("html_url", "")),
    }


def parse_version(tag: str) -> list:
    v = tag.lstrip("vV")
    parts = []
    for p in v.split(".")[:3]:
        try:
            parts.append(int("".join(ch for ch in p if ch.isdigit()) or "0"))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return parts


def is_newer_than_local(tag: str) -> bool:
    return parse_version(tag) > parse_version(APP_VERSION)
