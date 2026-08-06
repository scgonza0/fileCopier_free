import os
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Callable
from PySide6.QtCore import QObject, Signal
from .models import FileInfo
from .filter_engine import match
from .logger import log_scan, log_expand_dir, log_error, log

_SCAN_CACHE: dict = {}
_SCAN_CACHE_TTL = 60  # seconds


def _stat(path) -> tuple:
    """os.stat robusto: reintenta con prefijo de ruta larga (\\\\?\\) en Windows."""
    try:
        st = os.stat(path)
        return st.st_size, datetime.fromtimestamp(st.st_mtime)
    except OSError:
        try:
            if os.name == "nt" and not str(path).startswith("\\\\?\\"):
                st = os.stat("\\\\?\\" + str(Path(path).resolve()))
                return st.st_size, datetime.fromtimestamp(st.st_mtime)
        except OSError:
            pass
        return 0, datetime.min


def ensure_real_info(fi) -> "FileInfo":
    """Re-estadiza un FileInfo si parece placeholder (0B o fecha mínima)."""
    if fi.size != 0 or fi.modified != datetime.min:
        return fi
    size, modified = _stat(fi.path)
    if modified != datetime.min:
        fi.size = size
        fi.modified = modified
    return fi


def _scandir_entry_to_info(root: Path, entry: os.DirEntry) -> Optional[FileInfo]:
    try:
        stat = entry.stat()
        rel = Path(entry.path).relative_to(root)
        ext = os.path.splitext(entry.name)[1].lower()
        return FileInfo(
            path=Path(entry.path),
            name=entry.name,
            size=stat.st_size if entry.is_file() else 0,
            modified=datetime.fromtimestamp(stat.st_mtime),
            is_dir=entry.is_dir(),
            relative_path=rel.as_posix(),
            extension=ext,
        )
    except (OSError, ValueError):
        return None


def scan_level(
    root: Path,
    current_dir: Path,
    show_exts: Optional[List[str]] = None,
    hide_keywords: Optional[List[str]] = None,
) -> List[FileInfo]:
    t0 = time.time()
    root = root.resolve()
    entries = []

    try:
        scandir_iter = os.scandir(str(current_dir))
    except PermissionError:
        return entries

    raw = []
    with scandir_iter as it:
        for entry in it:
            try:
                name_lower = entry.name.lower()
                if hide_keywords and any(kw in name_lower for kw in hide_keywords):
                    continue
                if entry.is_file() and show_exts:
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in show_exts:
                        continue
                raw.append(entry)
            except OSError:
                continue

    raw.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

    for entry in raw:
        fi = _scandir_entry_to_info(root, entry)
        if fi:
            entries.append(fi)

    elapsed = time.time() - t0
    if elapsed > 0.1:
        log_expand_dir(str(current_dir), len(raw), elapsed)

    return entries


class ScanWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)  # List[FileInfo] (ya filtrados si hay preset)

    def __init__(self, root: Path, preset=None, parent=None):
        super().__init__(parent)
        self.root = root
        self.preset = preset
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _check_cancel(self):
        if self._cancelled:
            raise _ScanCancelled

    def run(self):
        try:
            all_files = scan_full(self.root, self._on_progress, preset=self.preset)
            self._check_cancel()
            if self.preset is not None:
                result = match(self.preset, all_files, self._on_progress)
            else:
                result = all_files
            if not self._cancelled:
                log(f"ScanWorker: emitiendo finished con {len(result)} archivos")
                self.finished.emit(result)
        except _ScanCancelled:
            log("ScanWorker: cancelado por el usuario")
            self.finished.emit([])
        except Exception as e:
            log_error(f"ScanWorker: {e}")
            self.finished.emit([])

    def _on_progress(self, cur, total):
        if self._cancelled:
            raise _ScanCancelled
        self.progress.emit(cur, total)


class MatchWorker(QObject):
    """Match an already-scanned list of files in a background thread."""
    progress = Signal(int, int)
    finished = Signal(object)  # List[FileInfo]

    def __init__(self, preset, files: List[FileInfo], parent=None):
        super().__init__(parent)
        self.preset = preset
        self.files = files
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = match(self.preset, self.files, self._on_progress)
            if not self._cancelled:
                log(f"MatchWorker: emitiendo finished con {len(result)} archivos")
                self.finished.emit(result)
        except _ScanCancelled:
            log("MatchWorker: cancelado por el usuario")
            self.finished.emit([])
        except Exception as e:
            log_error(f"MatchWorker: {e}")
            self.finished.emit([])

    def _on_progress(self, cur, total):
        if self._cancelled:
            raise _ScanCancelled
        self.progress.emit(cur, total)


class _ScanCancelled(Exception):
    pass


def scan_full(
    root: Path,
    progress_callback: Optional[Callable] = None,
    preset=None,
) -> List[FileInfo]:
    """Escaneo completo siempre con stat, así tamaño y fecha son reales."""
    t0 = time.time()
    root = root.resolve()
    str_root = str(root)

    cache_key = f"{str_root}|full"
    if cache_key in _SCAN_CACHE:
        ts, cached = _SCAN_CACHE[cache_key]
        if time.time() - ts < _SCAN_CACHE_TTL:
            log(f"scan_full CACHE HIT: {cache_key} -> {len(cached)} items")
            if progress_callback:
                progress_callback(len(cached), len(cached))
            return cached

    log(f"scan_full INICIO: {cache_key}")
    entries: List[FileInfo] = []
    processed = 0

    try:
        for dirpath, dirnames, filenames in os.walk(str_root):
            dirnames.sort(key=str.lower)
            filenames.sort(key=str.lower)

            for name in dirnames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, str_root).replace("\\", "/")
                size, modified = _stat(full)
                entries.append(FileInfo(
                    path=Path(full),
                    name=name,
                    size=0,
                    modified=modified,
                    is_dir=True,
                    relative_path=rel,
                    extension="",
                ))
                processed += 1
                if progress_callback and processed % 20000 == 0:
                    progress_callback(processed, 0)

            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, str_root).replace("\\", "/")
                ext = os.path.splitext(name)[1].lower()
                size, modified = _stat(full)
                entries.append(FileInfo(
                    path=Path(full),
                    name=name,
                    size=size,
                    modified=modified,
                    is_dir=False,
                    relative_path=rel,
                    extension=ext,
                ))
                processed += 1
                if progress_callback and processed % 20000 == 0:
                    progress_callback(processed, 0)
    except PermissionError:
        pass

    if progress_callback:
        progress_callback(processed, processed)

    _SCAN_CACHE[cache_key] = (time.time(), entries)

    elapsed = time.time() - t0
    log(f"scan_full FIN: {len(entries)} items en {elapsed:.2f}s")
    log_scan(str_root, len(entries), elapsed)

    return entries
