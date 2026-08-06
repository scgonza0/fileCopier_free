import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QFileIconProvider,
    QAbstractItemView, QWidget, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal
from core.models import FileInfo
from core.scanner import scan_level, ensure_real_info
from core.copier import format_size
from core.logger import log_load_tree, log_info, log_error, log


UNLOADED = "unloaded"

LARGE_DIR_THRESHOLD = 800


class FileTreeWidget(QTreeWidget):
    selection_changed = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setHeaderLabels(["Nombre", "Tamaño", "Modificado"])
        self.setColumnWidth(0, 400)
        self.setColumnWidth(1, 100)
        self.setColumnWidth(2, 150)
        self.setIndentation(20)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setIconSize(self.iconSize())
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.root_path: Optional[Path] = None
        self._file_item_map: Dict[str, QTreeWidgetItem] = {}
        self._dir_count = 0
        self._show_exts: Optional[List[str]] = None
        self._hide_keywords: Optional[List[str]] = None
        self._updating_checks = 0

        ip = QFileIconProvider()
        self._folder_icon = ip.icon(QFileIconProvider.Folder)
        self._file_icon = ip.icon(QFileIconProvider.File)

        self.itemExpanded.connect(self._on_item_expanded)
        self.itemChanged.connect(self._on_item_changed)

    def load_root(
        self,
        root: Path,
        show_exts: Optional[List[str]] = None,
        hide_keywords: Optional[List[str]] = None,
        preserve_state: bool = False,
    ):
        t0 = time.time()
        saved_checks: Set[str] = set()
        saved_expanded: Set[str] = set()
        if preserve_state:
            for i in range(self.topLevelItemCount()):
                self._collect_checks(self.topLevelItem(i), saved_checks)
                self._save_expanded(self.topLevelItem(i), saved_expanded)

        self.clear()
        self._file_item_map = {}
        self._dir_count = 0
        self.root_path = root
        self._show_exts = show_exts
        self._hide_keywords = hide_keywords

        entries = scan_level(root, root, show_exts, hide_keywords)
        self._updating_checks += 1
        for idx, e in enumerate(entries):
            self._build_item(self, e)
            if idx % 100 == 0:
                QApplication.processEvents()

        if saved_checks or saved_expanded:
            for i in range(self.topLevelItemCount()):
                if saved_checks:
                    self._restore_checks(self.topLevelItem(i), saved_checks)
                if saved_expanded:
                    self._restore_expanded(self.topLevelItem(i), saved_expanded)
        self._updating_checks -= 1

        elapsed = time.time() - t0
        log_load_tree(str(root), len(self._file_item_map), elapsed)
        self.selection_changed.emit()

    def _collect_checks(self, item: QTreeWidgetItem, acc: Set[str]):
        if item.checkState(0) == Qt.Checked:
            acc.add(item.data(0, Qt.UserRole))
        for i in range(item.childCount()):
            self._collect_checks(item.child(i), acc)

    def _restore_checks(self, item: QTreeWidgetItem, saved: Set[str]):
        if item.data(0, Qt.UserRole) in saved:
            item.setCheckState(0, Qt.Checked)
        for i in range(item.childCount()):
            self._restore_checks(item.child(i), saved)

    def _save_expanded(self, item: QTreeWidgetItem, acc: Set[str]):
        if item.isExpanded():
            acc.add(item.data(0, Qt.UserRole))
        for i in range(item.childCount()):
            self._save_expanded(item.child(i), acc)

    def _restore_expanded(self, item: QTreeWidgetItem, saved: Set[str]):
        if item.data(0, Qt.UserRole) in saved:
            item.setExpanded(True)
        for i in range(item.childCount()):
            self._restore_expanded(item.child(i), saved)

    def _build_item(self, parent, e: FileInfo):
        item = QTreeWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

        item.setIcon(0, self._folder_icon if e.is_dir else self._file_icon)
        item.setText(0, e.name)
        item.setText(2, e.modified.strftime("%Y-%m-%d %H:%M"))
        item.setData(0, Qt.UserRole, e.relative_path)
        item.setData(0, Qt.UserRole + 1, e)

        if isinstance(parent, QTreeWidgetItem):
            item.setCheckState(0, parent.checkState(0))
        else:
            item.setCheckState(0, Qt.Unchecked)

        if e.is_dir:
            self._dir_count += 1
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.setData(0, Qt.UserRole + 2, UNLOADED)
        else:
            ensure_real_info(e)
            item.setText(1, format_size(e.size))
            self._file_item_map[e.relative_path] = item

        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        if item.data(0, Qt.UserRole + 2) != UNLOADED:
            return

        item.setData(0, Qt.UserRole + 2, None)
        rel = item.data(0, Qt.UserRole)
        if not rel:
            return

        full_path = self.root_path / rel
        log(f"Expandiendo carpeta: {rel}")
        t0 = time.time()

        # Quick size check before loading
        try:
            estimated = sum(1 for _ in os.scandir(str(full_path)))
            if estimated > LARGE_DIR_THRESHOLD:
                reply = QMessageBox.question(
                    self, "Directorio grande",
                    f"Esta carpeta contiene ~{estimated} elementos.\n"
                    f"¿Cargar de todos modos?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
        except (PermissionError, OSError):
            pass

        entries = scan_level(self.root_path, full_path, self._show_exts, self._hide_keywords)
        self._updating_checks += 1
        for idx, e in enumerate(entries):
            self._build_item(item, e)
            if idx % 100 == 0:
                QApplication.processEvents()
        self._updating_checks -= 1
        log(f"Carpeta expandida: {rel} → {len(entries)} entradas en {time.time()-t0:.2f}s")

    def _load_all_descendants(self, item: QTreeWidgetItem, _counter=None):
        if _counter is None:
            _counter = [0]
        if item.data(0, Qt.UserRole + 2) == UNLOADED:
            item.setData(0, Qt.UserRole + 2, None)
            rel = item.data(0, Qt.UserRole)
            if rel and self.root_path:
                full_path = self.root_path / rel
                entries = scan_level(self.root_path, full_path, self._show_exts, self._hide_keywords)
                for e in entries:
                    self._build_item(item, e)
                    _counter[0] += 1
                    if _counter[0] % 100 == 0:
                        QApplication.processEvents()
        for i in range(item.childCount()):
            self._load_all_descendants(item.child(i), _counter)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0 or self._updating_checks > 0:
            return
        try:
            self._updating_checks += 1
            state = item.checkState(0)
            if state == Qt.Checked:
                self._load_all_descendants(item)
            self._set_children_state(item, state)
            selected = self.selectedItems()
            if len(selected) > 1 and item in selected:
                for sel in selected:
                    if sel is not item and (sel.flags() & Qt.ItemIsUserCheckable):
                        if state == Qt.Checked:
                            self._load_all_descendants(sel)
                        sel.setCheckState(0, state)
                        self._set_children_state(sel, state)
            self._updating_checks -= 1
        except Exception as e:
            self._updating_checks = max(0, self._updating_checks - 1)
            log_error(f"_on_item_changed: {e}")
        self.selection_changed.emit()

    def _set_children_state(self, parent: QTreeWidgetItem, state):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                child.setCheckState(0, state)
            self._set_children_state(child, state)

    def get_selected_file_infos(self) -> List[FileInfo]:
        result = []
        for rel, item in self._file_item_map.items():
            if item.checkState(0) == Qt.Checked:
                fi = item.data(0, Qt.UserRole + 1)
                if fi:
                    result.append(fi)
        return result

    def has_hidden_selected(self) -> bool:
        for rel, item in self._file_item_map.items():
            if item.checkState(0) == Qt.Checked and item.isHidden():
                return True
        return False

    def get_all_loaded_file_infos(self) -> List[FileInfo]:
        result = []
        for item in self._file_item_map.values():
            fi = item.data(0, Qt.UserRole + 1)
            if fi:
                result.append(fi)
        return result

    def expand_to_path(self, relative_path: str) -> Optional[QTreeWidgetItem]:
        """Walk the tree, expand dirs to reach file. Loads children bypassing filters."""
        parts = relative_path.split("/")
        current = self.invisibleRootItem()  # QTreeWidgetItem
        built_path = ""

        for i, part in enumerate(parts):
            built_path = f"{built_path}/{part}" if built_path else part
            is_last = (i == len(parts) - 1)

            child = None
            for j in range(current.childCount()):
                c = current.child(j)
                if c.data(0, Qt.UserRole) == built_path:
                    child = c
                    break

            if child is None:
                return None

            if is_last:
                if child in self._file_item_map.values():
                    return child
                return None  # file not loaded / not a real file

            # It's a directory: force-load if unloaded, then expand
            if child.data(0, Qt.UserRole + 2) == UNLOADED:
                child.setData(0, Qt.UserRole + 2, None)
                dir_path = self.root_path / built_path
                entries = scan_level(self.root_path, dir_path, None, None)
                self._updating_checks += 1
                for e in entries:
                    self._build_item(child, e)
                self._updating_checks -= 1

            child.setExpanded(True)
            current = child

        return None

    def batch_check_files(self, files, checked: bool, progress_cb=None, cancel_flag=None):
        """Aplica estado de check a muchos archivos. Carga en el árbol la cadena
        completa de carpetas de cada archivo aunque no estuviera expandido."""
        log(f"batch_check_files: {len(files)} archivos, checked={checked}")
        target = Qt.Checked if checked else Qt.Unchecked
        total = len(files)
        done = 0
        self._updating_checks += 1
        for fi in files:
            if cancel_flag is not None and cancel_flag.is_set():
                break
            item = self._ensure_file_item(fi)
            if item is not None:
                item.setCheckState(0, target)
            done += 1
            if done % 100 == 0:
                QApplication.processEvents()
                if progress_cb:
                    progress_cb(done, total)
        self._updating_checks -= 1
        if progress_cb:
            progress_cb(done, total)
        log(f"batch_check_files terminó: {done}/{total} procesados")
        self.selection_changed.emit()
        return done

    def apply_checked_files(self, file_states, progress_cb=None, cancel_flag=None):
        """Carga cada archivo en el árbol y le aplica su estado de check.
        file_states: iterable de tuplas (FileInfo, checked: bool)."""
        total = len(file_states)
        done = 0
        self._updating_checks += 1
        for fi, checked in file_states:
            if cancel_flag is not None and cancel_flag.is_set():
                break
            item = self._ensure_file_item(fi)
            if item is not None:
                item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            done += 1
            if done % 100 == 0:
                QApplication.processEvents()
                if progress_cb:
                    progress_cb(done, total)
        self._updating_checks -= 1
        if progress_cb:
            progress_cb(done, total)
        log(f"apply_checked_files: {done}/{total} aplicados")
        self.selection_changed.emit()
        return done

    def _find_child(self, parent, built_path: str) -> Optional[QTreeWidgetItem]:
        if isinstance(parent, QTreeWidgetItem):
            count = parent.childCount()
            get = lambda j: parent.child(j)
        else:
            count = self.topLevelItemCount()
            get = lambda j: self.topLevelItem(j)
        for j in range(count):
            c = get(j)
            if c.data(0, Qt.UserRole) == built_path:
                return c
        return None

    def _ensure_file_item(self, fi: FileInfo) -> Optional[QTreeWidgetItem]:
        """Garantiza que exista el item del archivo en el árbol, creando la
        cadena de carpetas intermedia si hace falta. Devuelve el item."""
        existing = self._file_item_map.get(fi.relative_path)
        if existing is not None:
            return existing
        if self.root_path is None:
            return None

        parts = fi.relative_path.split("/")
        parent = self  # QTreeWidget (nivel superior)
        built = ""

        for i, part in enumerate(parts):
            built = f"{built}/{part}" if built else part
            is_last = (i == len(parts) - 1)
            child = self._find_child(parent, built)

            if child is None:
                if is_last:
                    self._build_item(parent, fi)
                    return self._file_item_map.get(fi.relative_path)
                try:
                    st = os.stat(self.root_path / Path(built))
                    mod = datetime.fromtimestamp(st.st_mtime)
                except OSError:
                    mod = fi.modified
                e = FileInfo(
                    path=self.root_path / Path(built),
                    name=part,
                    size=0,
                    modified=mod,
                    is_dir=True,
                    relative_path=built,
                    extension="",
                )
                self._build_item(parent, e)
                child = self._find_child(parent, built)
                child.setData(0, Qt.UserRole + 2, None)  # marcado como cargado
            elif not is_last and child.data(0, Qt.UserRole + 2) == UNLOADED:
                child.setData(0, Qt.UserRole + 2, None)

            if not is_last:
                child.setExpanded(True)
            parent = child

        return None

    def _set_check_recursive(self, item: QTreeWidgetItem, state):
        """Recursively set check state. Only loads descendants when checking
        (deselect solo desmarca lo ya cargado, así es rápido)."""
        if state == Qt.Checked:
            self._load_all_descendants(item)
        if item.flags() & Qt.ItemIsUserCheckable:
            item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_check_recursive(item.child(i), state)

    def check_all(self, state: bool):
        log(f"check_all({'marcar' if state else 'desmarcar'})")
        self._updating_checks += 1
        check = Qt.Checked if state else Qt.Unchecked
        for i in range(self.topLevelItemCount()):
            self._set_check_recursive(self.topLevelItem(i), check)
        self._updating_checks -= 1
        self.selection_changed.emit()

    def get_visible_count(self) -> int:
        return len(self._file_item_map)

    def get_folder_count(self) -> int:
        return self._dir_count

    def apply_filter_visibility(self, show_exts=None, hide_keywords=None):
        log(f"apply_filter_visibility: show={show_exts} hide={hide_keywords}")
        self._updating_checks += 1
        for i in range(self.topLevelItemCount()):
            self._show_all(self.topLevelItem(i))
        for i in range(self.topLevelItemCount()):
            self._apply_filter_to_item(self.topLevelItem(i), show_exts, hide_keywords)
        self._updating_checks -= 1
        self.selection_changed.emit()

    def _show_all(self, item: QTreeWidgetItem):
        item.setHidden(False)
        for i in range(item.childCount()):
            self._show_all(item.child(i))

    def _apply_filter_to_item(self, item: QTreeWidgetItem, show_exts, hide_keywords):
        rel = (item.data(0, Qt.UserRole) or "").lower()
        is_dir = item.childIndicatorPolicy() == QTreeWidgetItem.ShowIndicator

        hidden = False
        if hide_keywords:
            if any(kw in rel for kw in hide_keywords):
                hidden = True
        if not hidden and not is_dir and show_exts:
            ext = Path(rel).suffix.lower()
            if ext not in show_exts:
                hidden = True

        item.setHidden(hidden)
        if not hidden:
            for i in range(item.childCount()):
                self._apply_filter_to_item(item.child(i), show_exts, hide_keywords)
