import time
import os
import sys
import threading
import traceback
from functools import wraps
from pathlib import Path

_LOG_FILE: Path = None
_LOCK = threading.Lock()
_start_time = time.time()


def _default_log_path() -> Path:
    # Log privado del usuario: %APPDATA%\FileCopier\fileCopier_log.txt
    try:
        from .config import log_path
        return log_path()
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent / "fileCopier_log.txt"


def get_log_path() -> Path:
    global _LOG_FILE
    if _LOG_FILE is None:
        _LOG_FILE = _default_log_path()
    return _LOG_FILE


def init_log():
    global _LOG_FILE
    _LOG_FILE = _default_log_path()
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > 5 * 1024 * 1024:
            _LOG_FILE.unlink()
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n=== Sesión {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(f"Python: {sys.version.split()[0]} | frozen: {getattr(sys, 'frozen', False)} | argv={sys.argv}\n\n")
            f.flush()
    except Exception:
        pass
    log_info("Logger iniciado")


def _log(category: str, message: str):
    elapsed = time.time() - _start_time
    timestamp = time.strftime("%H:%M:%S")
    try:
        thread_name = threading.current_thread().name
    except Exception:
        thread_name = "?"
    line = f"[{timestamp} +{elapsed:7.1f}s] [{category:8s}] [{thread_name}] {message}"
    try:
        with _LOCK:
            with open(get_log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
    except Exception:
        pass
    # Consola SOLO si se pide explícitamente (evita ruido en el exe)
    if os.environ.get("FILECOPIER_DEBUG"):
        try:
            print(line, flush=True)
        except Exception:
            pass


def log(msg: str):
    _log("INFO", msg)


def log_info(msg: str):
    _log("INFO", msg)


def log_error(msg: str):
    _log("ERROR", msg)


def log_exception(msg: str = ""):
    tb = traceback.format_exc()
    _log("ERROR", f"{msg}\n{tb}")


def log_scan(root: str, file_count: int, elapsed: float):
    _log("SCAN", f"Raíz={root} | {file_count} archivos | {elapsed:.2f}s")


def log_match(rule_count: int, file_in: int, file_out: int, elapsed: float):
    _log("MATCH", f"{rule_count} reglas | {file_in} in → {file_out} out | {elapsed:.3f}s")


def log_load_tree(root: str, file_count: int, elapsed: float):
    _log("TREE", f"Raíz={root} | {file_count} archivos visibles | {elapsed:.2f}s")


def log_expand_dir(path: str, entry_count: int, elapsed: float):
    _log("EXPAND", f"{path} | {entry_count} entradas | {elapsed:.2f}s")


def log_copy(files: int, dest: str, flat: bool, elapsed: float, ok: int, err: int):
    _log("COPY", f"{files} archivos -> {dest} | flat={flat} | {elapsed:.2f}s | {ok} OK {err} ERR")


def log_age_days() -> float:
    """Edad del log en días. -1 si no existe."""
    try:
        p = get_log_path()
        if p.exists():
            return (time.time() - p.stat().st_mtime) / 86400.0
    except Exception:
        pass
    return -1.0


def delete_log():
    try:
        get_log_path().unlink(missing_ok=True)
    except Exception:
        pass


def safe(fn):
    """Decorator for UI slots: catches exceptions, logs them, shows a message box,
    and prevents the app from silently crashing on unhandled slot exceptions."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log_exception(f"ERROR en {getattr(fn, '__name__', str(fn))}: {e}")
            try:
                from PySide6.QtWidgets import QMessageBox, QApplication
                widget = args[0] if args else None
                if widget is not None and hasattr(widget, "isWidgetType") and widget.isWidgetType():
                    parent = widget
                else:
                    parent = None
                QMessageBox.critical(
                    parent, "Error",
                    f"Ocurrió un error inesperado:\n{e}\n\nDetalles en el archivo de log."
                )
            except Exception:
                pass
    return wrapper
