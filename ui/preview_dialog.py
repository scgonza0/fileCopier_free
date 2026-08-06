from pathlib import Path
from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileIconProvider, QApplication,
    QProgressDialog,
)
from PySide6.QtCore import Qt
from core.models import FileInfo
from core.copier import format_size
from core.i18n import T

PAGE_MAX = 20000


class PreviewDialog(QDialog):
    def __init__(self, matched: List[FileInfo], main_tree: "FileTreeWidget", parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Preview - Matching files"))
        self.setMinimumSize(750, 500)

        self._matched = sorted(matched, key=lambda f: f.relative_path)
        self._main_tree = main_tree
        self._pages = self._build_pages()
        self._page_idx = 0
        self._updating_preview = 0

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(T("files match the filter", n=len(matched))))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Name"), T("Size"), T("Modified")])
        self.tree.setColumnWidth(0, 350)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 150)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(20)
        self.tree.itemChanged.connect(self._on_preview_changed)

        layout.addWidget(self.tree, 1)

        # Pagination bar
        nav_row = QHBoxLayout()
        self.btn_prev = QPushButton("◀ " + T("Previous"))
        self.btn_prev.clicked.connect(self._prev_page)
        nav_row.addWidget(self.btn_prev)
        self.nav_label = QLabel("")
        self.nav_label.setAlignment(Qt.AlignCenter)
        nav_row.addWidget(self.nav_label, 1)
        self.btn_next = QPushButton(T("Next") + " ▶")
        self.btn_next.clicked.connect(self._next_page)
        nav_row.addWidget(self.btn_next)
        layout.addLayout(nav_row)

        btn_row = QHBoxLayout()
        btn_select_all = QPushButton(T("Select all"))
        btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton(T("Deselect all"))
        btn_deselect_all.clicked.connect(self._deselect_all)
        btn_row.addWidget(btn_deselect_all)

        btn_row.addStretch()

        btn_apply = QPushButton(T("Apply to main tree"))
        btn_apply.clicked.connect(self._apply_selection)
        btn_row.addWidget(btn_apply)

        btn_close = QPushButton(T("Close"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._render_page()

    # ── pagination ─────────────────────────────────────────

    def _build_pages(self) -> List[list]:
        groups = []
        index: Dict[str, list] = {}
        for fi in self._matched:
            parent = fi.relative_path.rpartition("/")[0]
            if parent in index:
                index[parent].append(fi)
            else:
                index[parent] = [fi]
                groups.append((parent, index[parent]))

        pages = []
        current = []
        current_count = 0
        for parent, files in groups:
            if current and current_count + len(files) > PAGE_MAX:
                pages.append(current)
                current = []
                current_count = 0
            current.append((parent, files))
            current_count += len(files)
        if current:
            pages.append(current)
        return pages

    def _page_count(self, page) -> int:
        return sum(len(files) for _, files in page)

    def _update_nav(self):
        total = len(self._matched)
        count = self._page_count(self._pages[self._page_idx])
        start = sum(self._page_count(p) for p in self._pages[: self._page_idx])
        end = start + count
        self.nav_label.setText(
            T("Page {cur} of {total} · files {start}-{end} (of {total_files})",
              cur=self._page_idx + 1, total=len(self._pages),
              start=start + 1, end=end, total_files=total)
        )
        self.btn_prev.setEnabled(self._page_idx > 0)
        self.btn_next.setEnabled(self._page_idx < len(self._pages) - 1)

    def _prev_page(self):
        if self._page_idx > 0:
            self._page_idx -= 1
            self._render_page()

    def _next_page(self):
        if self._page_idx < len(self._pages) - 1:
            self._page_idx += 1
            self._render_page()

    # ── tree building ──────────────────────────────────────

    def _render_page(self):
        self.tree.clear()
        QApplication.processEvents()

        ip = QFileIconProvider()
        folder_icon = ip.icon(QFileIconProvider.Folder)
        file_icon = ip.icon(QFileIconProvider.File)

        dir_items: Dict[str, QTreeWidgetItem] = {}
        file_items: List[QTreeWidgetItem] = []

        for _parent, files in self._pages[self._page_idx]:
            for fi in files:
                parts = fi.relative_path.split("/")
                parent_item: Optional[QTreeWidgetItem] = None
                built = ""

                for i, part in enumerate(parts):
                    built = f"{built}/{part}" if built else part
                    is_last = (i == len(parts) - 1)

                    if not is_last:
                        if built not in dir_items:
                            d = QTreeWidgetItem()
                            d.setIcon(0, folder_icon)
                            d.setText(0, part)
                            d.setFlags(d.flags() | Qt.ItemIsUserCheckable)
                            d.setCheckState(0, Qt.Checked)
                            d.setData(0, Qt.UserRole, built)
                            dir_items[built] = d
                            if parent_item is not None:
                                parent_item.addChild(d)
                        parent_item = dir_items[built]
                    else:
                        item = QTreeWidgetItem()
                        item.setIcon(0, file_icon)
                        item.setText(0, part)
                        item.setText(1, format_size(fi.size))
                        item.setText(2, fi.modified.strftime("%Y-%m-%d %H:%M"))
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.Checked)
                        item.setData(0, Qt.UserRole, fi.relative_path)
                        file_items.append(item)
                        if parent_item is not None:
                            parent_item.addChild(item)

        for path_so_far, d in dir_items.items():
            parent_path = str(Path(path_so_far).parent).replace("\\", "/")
            if parent_path == "." or parent_path not in dir_items:
                self.tree.addTopLevelItem(d)
            else:
                dir_items[parent_path].addChild(d)

        for item in file_items:
            if not item.parent():
                self.tree.addTopLevelItem(item)

        self.tree.expandAll()
        self._update_nav()

    # ── selection handling ─────────────────────────────────

    def _on_preview_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0 or self._updating_preview > 0:
            return
        state = item.checkState(0)
        for i in range(item.childCount()):
            child = item.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                child.setCheckState(0, state)

    def _set_all_states(self, state):
        self._updating_preview += 1

        def rec(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.flags() & Qt.ItemIsUserCheckable:
                    child.setCheckState(0, state)
                rec(child)

        rec(self.tree.invisibleRootItem())
        self._updating_preview -= 1

    def _select_all(self):
        self._set_all_states(Qt.Checked)

    def _deselect_all(self):
        self._set_all_states(Qt.Unchecked)

    def _collect_states(self, parent, rel_to_fi, out):
        for i in range(parent.childCount()):
            child = parent.child(i)
            rel = child.data(0, Qt.UserRole)
            is_dir = child.childCount() > 0
            if is_dir:
                self._collect_states(child, rel_to_fi, out)
            else:
                fi = rel_to_fi.get(rel)
                if fi is not None:
                    out.append((fi, child.checkState(0) == Qt.Checked))

    def _apply_selection(self):
        rel_to_fi = {f.relative_path: f for f in self._matched}
        states = []
        self._collect_states(self.tree.invisibleRootItem(), rel_to_fi, states)
        if not states:
            self.accept()
            return

        import threading
        cancel_flag = threading.Event()
        progress = QProgressDialog(T("Apply to main tree"), T("Cancel"), 0, len(states), self)
        progress.setWindowTitle(T("Applying"))
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(lambda: cancel_flag.set())
        progress.show()

        def cb(cur, total):
            progress.setValue(cur)
            progress.setLabelText(f"Aplicando... {cur:,} / {total:,}")

        self._main_tree.apply_checked_files(states, cb, cancel_flag)
        progress.close()
        self.accept()
