from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QTreeWidget, QTreeWidgetItem,
    QFileIconProvider, QMessageBox, QCheckBox, QWidget
)
from PySide6.QtCore import Qt
from core.models import FileInfo
from core.copier import find_duplicate_names, format_size
from core.i18n import T


class CopyOptionsDialog(QDialog):
    def __init__(self, files: List[FileInfo], parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Copy options"))
        self.setMinimumSize(500, 400)

        self.files = files
        self.flat = False
        self.dup_action = "rename"

        layout = QVBoxLayout(self)

        # Mode
        mode_group = QVBoxLayout()
        mode_group.addWidget(QLabel(T("Copy mode")))
        self._mode_group = QButtonGroup(self)
        self.rb_structure = QRadioButton(T("Preserve folder structure"))
        self.rb_structure.setChecked(True)
        self.rb_flat = QRadioButton(T("Flat copy (rename duplicates)"))
        self._mode_group.addButton(self.rb_structure, 1)
        self._mode_group.addButton(self.rb_flat, 2)
        self.rb_flat.toggled.connect(self._on_mode_changed)
        mode_group.addWidget(self.rb_structure)
        mode_group.addWidget(self.rb_flat)
        layout.addLayout(mode_group)

        # Duplicate section (shown only when flat + dups exist)
        self._dup_section = QWidget()
        dup_layout = QVBoxLayout(self._dup_section)
        dup_layout.setContentsMargins(0, 0, 0, 0)

        dup_label = QLabel(T("Files with duplicate names:"))
        dup_layout.addWidget(dup_label)

        self._dup_tree = QTreeWidget()
        self._dup_tree.setHeaderLabels([T("File"), T("Path")])
        self._dup_tree.setColumnWidth(0, 200)
        self._dup_tree.setAlternatingRowColors(True)
        dup_layout.addWidget(self._dup_tree)

        dup_actions_row = QHBoxLayout()
        self.rb_dup_rename = QRadioButton(T("Rename automatically"))
        self.rb_dup_rename.setChecked(True)
        self.rb_dup_skip = QRadioButton(T("Skip duplicates"))
        self._dup_actions_group = QButtonGroup(self)
        self._dup_actions_group.addButton(self.rb_dup_rename, 1)
        self._dup_actions_group.addButton(self.rb_dup_skip, 2)
        dup_actions_row.addWidget(self.rb_dup_rename)
        dup_actions_row.addWidget(self.rb_dup_skip)

        btn_info = QPushButton("?")
        btn_info.setFixedWidth(28)
        btn_info.setToolTip(T("rename info tooltip"))
        btn_info.clicked.connect(self._show_rename_explanation)
        dup_actions_row.addWidget(btn_info)
        dup_actions_row.addStretch()
        dup_layout.addLayout(dup_actions_row)

        self._dup_section.setVisible(False)
        layout.addWidget(self._dup_section)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton(T("OK"))
        btn_ok.clicked.connect(self._accept)
        btn_cancel = QPushButton(T("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        # Populate duplicates
        self._populate_dups()

    def _show_rename_explanation(self):
        QMessageBox.information(
            self, T("rename info tooltip"),
            T("rename_explanation"),
        )

    def _populate_dups(self):
        self._dup_tree.clear()
        dups = find_duplicate_names(self.files)
        ip = QFileIconProvider()
        file_icon = ip.icon(QFileIconProvider.File)
        if dups:
            for name, lst in dups.items():
                parent = QTreeWidgetItem()
                parent.setText(0, name)
                parent.setIcon(0, file_icon)
                parent.setText(1, T("files_count", n=len(lst)))
                parent.setExpanded(True)
                for fi in lst:
                    child = QTreeWidgetItem()
                    child.setText(0, "")
                    child.setText(1, fi.relative_path)
                    parent.addChild(child)
                self._dup_tree.addTopLevelItem(parent)

    def _on_mode_changed(self):
        is_flat = self.rb_flat.isChecked()
        dups = find_duplicate_names(self.files)
        has_dups = bool(dups) and is_flat
        self._dup_section.setVisible(has_dups)
        if not has_dups:
            self.adjustSize()

    def _accept(self):
        self.flat = self.rb_flat.isChecked()
        if self.rb_dup_rename.isChecked():
            self.dup_action = "rename"
        else:
            self.dup_action = "skip"
        self.accept()
