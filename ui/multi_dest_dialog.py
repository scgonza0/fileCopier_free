import os
from pathlib import Path
from typing import List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QFileIconProvider,
    QRadioButton, QButtonGroup, QGroupBox
)
from PySide6.QtCore import Qt
from core.i18n import T


UNLOADED = "unloaded"


class MultiDestDialog(QDialog):
    def __init__(self, initial_root: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Copy to multiple destinations"))
        self.setMinimumSize(650, 500)

        self.selected_destinations: List[str] = []
        self.flat = False

        layout = QVBoxLayout(self)

        # Root selector
        root_row = QHBoxLayout()
        root_row.addWidget(QLabel(T("Root:")))
        self._root_label = QLabel(initial_root or T("not selected"))
        root_row.addWidget(self._root_label, 1)
        self._btn_browse = QPushButton(T("Browse"))
        self._btn_browse.clicked.connect(self._browse_root)
        root_row.addWidget(self._btn_browse)
        layout.addLayout(root_row)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Name"), T("Full path")])
        self.tree.setColumnWidth(0, 250)
        self.tree.setAlternatingRowColors(True)
        ip = QFileIconProvider()
        self._folder_icon = ip.icon(QFileIconProvider.Folder)
        self.tree.itemExpanded.connect(self._on_expanded)
        layout.addWidget(self.tree, 1)

        # Select all / deselect all
        sel_row = QHBoxLayout()
        btn_sel_all = QPushButton(T("Select all"))
        btn_sel_all.clicked.connect(self._select_all)
        sel_row.addWidget(btn_sel_all)
        btn_desel_all = QPushButton(T("Deselect all"))
        btn_desel_all.clicked.connect(self._deselect_all)
        sel_row.addWidget(btn_desel_all)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Copy mode
        mode_group = QGroupBox(T("Copy mode"))
        mode_layout = QVBoxLayout(mode_group)
        self._mode_group = QButtonGroup(self)
        self.rb_structure = QRadioButton(T("Preserve folder structure"))
        self.rb_structure.setChecked(True)
        self.rb_flat = QRadioButton(T("Flat copy (rename duplicates)"))
        self._mode_group.addButton(self.rb_structure, 1)
        self._mode_group.addButton(self.rb_flat, 2)
        mode_layout.addWidget(self.rb_structure)
        mode_layout.addWidget(self.rb_flat)
        layout.addWidget(mode_group)

        # Buttons
        btn_row = QHBoxLayout()
        self._count_label = QLabel(T("{n} destinations selected", n=0))
        btn_row.addWidget(self._count_label)
        btn_row.addStretch()
        btn_ok = QPushButton(T("Copy to selected"))
        btn_ok.clicked.connect(self._accept)
        btn_cancel = QPushButton(T("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if initial_root and Path(initial_root).is_dir():
            self._load_root(initial_root)

    def _browse_root(self):
        path = QFileDialog.getExistingDirectory(self, T("Select a root folder"))
        if path:
            self._load_root(path)

    def _load_root(self, root_path: str):
        self._root_label.setText(root_path)
        self.tree.clear()
        root_item = QTreeWidgetItem()
        root_item.setText(0, Path(root_path).name)
        root_item.setText(1, root_path)
        root_item.setIcon(0, self._folder_icon)
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable)
        root_item.setCheckState(0, Qt.Unchecked)
        root_item.setData(0, Qt.UserRole, root_path)
        root_item.setData(0, Qt.UserRole + 1, UNLOADED)
        self.tree.addTopLevelItem(root_item)
        self._lazy_load_children(root_item)

    def _lazy_load_children(self, parent_item: QTreeWidgetItem):
        folder_path = parent_item.data(0, Qt.UserRole)
        if not folder_path:
            return
        try:
            with os.scandir(str(folder_path)) as it:
                entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
            parent_item.setData(0, Qt.UserRole + 1, None)
            for entry in entries:
                if entry.is_dir():
                    child = QTreeWidgetItem()
                    child.setIcon(0, self._folder_icon)
                    child.setText(0, entry.name)
                    child.setText(1, entry.path)
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.Unchecked)
                    child.setData(0, Qt.UserRole, entry.path)
                    child.setData(0, Qt.UserRole + 1, UNLOADED)
                    parent_item.addChild(child)
        except (PermissionError, OSError):
            pass

    def _on_expanded(self, item: QTreeWidgetItem):
        if item.data(0, Qt.UserRole + 1) == UNLOADED:
            self._lazy_load_children(item)

    def _collect_checked(self, item: QTreeWidgetItem, acc: List[str]):
        if item.checkState(0) == Qt.Checked:
            path = item.data(0, Qt.UserRole)
            if path:
                acc.append(path)
        for i in range(item.childCount()):
            self._collect_checked(item.child(i), acc)

    def _set_all(self, item: QTreeWidgetItem, state: Qt.CheckState):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_all(item.child(i), state)

    def _select_all(self):
        for i in range(self.tree.topLevelItemCount()):
            self._set_all(self.tree.topLevelItem(i), Qt.Checked)

    def _deselect_all(self):
        for i in range(self.tree.topLevelItemCount()):
            self._set_all(self.tree.topLevelItem(i), Qt.Unchecked)

    def _accept(self):
        self.selected_destinations = []
        for i in range(self.tree.topLevelItemCount()):
            self._collect_checked(self.tree.topLevelItem(i), self.selected_destinations)
        if not self.selected_destinations:
            self._count_label.setText(T("Select at least one destination"))
            self._count_label.setStyleSheet("color: red")
            return
        self.flat = self.rb_flat.isChecked()
        self.accept()
