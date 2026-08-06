import shutil
import os
import traceback
from pathlib import Path
from typing import List, Dict, Optional
from PySide6.QtCore import QObject, Signal
from .models import FileInfo
from .logger import log_error, log


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    else:
        return f"{size / 1024 ** 3:.2f} GB"


class CopyWorker(QObject):
    progress = Signal(int, int)
    file_copied = Signal(str, bool, str)
    finished = Signal()

    def __init__(self, files: List[FileInfo], dest_root: Path,
                 conflict_map: Optional[Dict[str, str]] = None,
                 flat: bool = False,
                 rename_map: Optional[Dict[str, str]] = None):
        super().__init__()
        self.files = files
        self.dest_root = dest_root
        self.conflict_map = conflict_map or {}
        self.flat = flat
        self.rename_map = rename_map or {}

    def run(self):
        try:
            total = len(self.files)
            results = []
            self.dest_root.mkdir(parents=True, exist_ok=True)
            log(f"CopyWorker INICIO: {total} archivos → {self.dest_root} flat={self.flat}")

            for i, f in enumerate(self.files):
                if self.flat:
                    dest = self.dest_root / self.rename_map.get(str(f.path), f.name)
                else:
                    dest = self.dest_root / f.relative_path

                success = True
                error = ""

                try:
                    if not self.flat:
                        dest.parent.mkdir(parents=True, exist_ok=True)

                    if dest.exists():
                        action = self.conflict_map.get(str(dest), "overwrite")
                        # un archivo que ya fue renombrado por duplicado nunca
                        # debe sobrescribir: se asegura un nombre único
                        if self.flat and str(f.path) in self.rename_map:
                            action = "rename"
                        if action == "skip":
                            self.file_copied.emit(str(f.path), True, "Omitido (ya existe)")
                            self.progress.emit(i + 1, total)
                            results.append((f, dest, True, "Omitido"))
                            continue
                        elif action == "rename":
                            dest = _unique_path(dest)

                    shutil.copy2(str(f.path), str(dest))
                    self.file_copied.emit(str(f.path), True, "")
                    results.append((f, dest, True, ""))
                except Exception as e:
                    error = str(e)
                    log_error(f"CopyWorker: error copiando {f.path} → {dest}: {e}")
                    self.file_copied.emit(str(f.path), False, error)
                    results.append((f, dest, False, error))

                self.progress.emit(i + 1, total)

            self._save_logs(results)
            ok = sum(1 for r in results if r[2])
            err = total - ok
            log(f"CopyWorker FIN: {ok} OK, {err} ERR")
        except Exception as e:
            log_error(f"CopyWorker.run: {e}\n{traceback.format_exc()}")
        finally:
            self.finished.emit()

    def _save_logs(self, results: list):
        source_log = self.dest_root / "source_files.log"
        dest_log = self.dest_root / "copied_files.log"

        with open(source_log, "w", encoding="utf-8") as f:
            f.write(f"# Archivos de origen - {self.dest_root}\n\n")
            for f_info, _, ok, _ in results:
                status = "[OK]" if ok else "[ERR]"
                f.write(f"{status} {f_info.path}\n")

        with open(dest_log, "w", encoding="utf-8") as f:
            f.write(f"# Archivos copiados a - {self.dest_root}\n\n")
            for f_info, dest, ok, _ in results:
                status = "[OK]" if ok else "[ERR]"
                f.write(f"{status} {dest}\n")


def _unique_path(path: Path) -> Path:
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        new = parent / f"{stem}({counter}){suffix}"
        if not new.exists():
            return new
        counter += 1


def check_conflicts(files: List[FileInfo], dest_root: Path,
                    flat: bool = False,
                    rename_map: Optional[Dict[str, str]] = None) -> List[tuple]:
    conflicts = []
    rename_map = rename_map or {}
    for f in files:
        if flat:
            dest = dest_root / rename_map.get(str(f.path), f.name)
        else:
            dest = dest_root / f.relative_path
        if dest.exists():
            conflicts.append((f.path, dest))
    return conflicts


def find_duplicate_names(files: List[FileInfo]) -> Dict[str, List[FileInfo]]:
    by_name: Dict[str, List[FileInfo]] = {}
    for f in files:
        by_name.setdefault(f.name, []).append(f)
    return {name: lst for name, lst in by_name.items() if len(lst) > 1}


def build_flat_rename_map(files: List[FileInfo]) -> Dict[str, str]:
    """Para nombres duplicados en copia plana: el de menor profundidad se toma
    como referencia (queda con su nombre). A cada duplicado se le agregan, en
    MAYÚSCULAS y unidas por '_', las carpetas de su ruta que no están en la
    referencia, pero SOLO las necesarias para que todos los nombres queden
    únicos (se descartan carpetas comunes como CODING/PRUEBA).
    Ej.: NEW_FOLDER_(2)_HEC032_NAVIGATION1
    Devuelve {ruta_origen_str: nuevo_nombre}."""
    groups = find_duplicate_names(files)
    if not groups:
        return {}
    planned = {f.name for f in files}
    rename_map: Dict[str, str] = {}
    for name, group in groups.items():
        dir_chains = [f.relative_path.split("/")[:-1] for f in group]
        order = sorted(range(len(group)),
                       key=lambda i: (len(dir_chains[i]), group[i].relative_path))
        base_chain = {c.lower() for c in dir_chains[order[0]]}
        tags = {i: [seg for seg in dir_chains[i] if seg.lower() not in base_chain]
                for i in order}
        tags = _minimize_tags(tags, order, name)
        for i in order[1:]:
            diff = tags[i]
            if not diff:
                new_name = _unique_name(name, planned)
            else:
                tag = "_".join(_sanitize_folder(s) for s in diff)
                new_name = _insert_before_ext(name, tag)
                if new_name in planned:
                    new_name = _unique_name(new_name, planned)
            planned.add(new_name)
            rename_map[str(group[i].path)] = new_name
    return rename_map


def _minimize_tags(tags: Dict[int, list], order: list, name: str) -> Dict[int, list]:
    """Quita de a uno los segmentos de carpeta que no son necesarios para que
    todos los duplicados del grupo sigan teniendo nombres únicos."""
    segments = []
    seen = set()
    for i in order[1:]:
        for seg in tags[i]:
            key = seg.lower()
            if key not in seen:
                seen.add(key)
                segments.append(seg)
    for seg in segments:
        test = {i: [s for s in tags[i] if s.lower() != seg.lower()]
                for i in tags}
        if _tags_unique(test, order, name):
            tags = test
    return tags


def _tags_unique(tags: Dict[int, list], order: list, name: str) -> bool:
    seen = set()
    for i in order:
        segs = tags[i]
        if not segs:
            nm = name
        else:
            nm = _insert_before_ext(name, "_".join(_sanitize_folder(s) for s in segs))
        if nm in seen:
            return False
        seen.add(nm)
    return True


def _sanitize_folder(name: str) -> str:
    return name.upper().replace(" ", "_").replace("-", "_")


def _insert_before_ext(name: str, tag: str) -> str:
    stem, ext = os.path.splitext(name)
    return f"{stem}_{tag}{ext}"


def _unique_name(name: str, planned: set) -> str:
    stem, ext = os.path.splitext(name)
    i = 1
    while True:
        cand = f"{stem}({i}){ext}"
        if cand not in planned:
            return cand
        i += 1
