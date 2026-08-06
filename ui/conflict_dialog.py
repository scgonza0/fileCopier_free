from pathlib import Path
from typing import List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QRadioButton, QButtonGroup, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt
from core.i18n import T


class ConflictDialog(QDialog):
    def __init__(self, conflicts: List[Tuple[Path, Path]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Conflicts - Existing files"))
        self.setMinimumSize(600, 350)
        self.conflicts = conflicts
        self._decision = "overwrite"

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(T("conflicts exist", n=len(conflicts))))

        table = QTableWidget(len(conflicts), 2)
        table.setHorizontalHeaderLabels([T("Source"), T("Destination")])
        table.horizontalHeader().setStretchLastSection(True)
        for i, (src, dst) in enumerate(conflicts):
            table.setItem(i, 0, QTableWidgetItem(str(src)))
            table.setItem(i, 1, QTableWidgetItem(str(dst)))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        layout.addWidget(table)

        group_layout = QVBoxLayout()
        group_layout.addWidget(QLabel(T("Action for all conflicts:")))

        self.group = QButtonGroup(self)
        rb_overwrite = QRadioButton(T("Overwrite"))
        rb_skip = QRadioButton(T("Skip"))
        rb_rename = QRadioButton(T("Rename automatically"))

        self.group.addButton(rb_overwrite, 1)
        self.group.addButton(rb_skip, 2)
        self.group.addButton(rb_rename, 3)
        rb_overwrite.setChecked(True)

        group_layout.addWidget(rb_overwrite)
        group_layout.addWidget(rb_skip)
        group_layout.addWidget(rb_rename)
        layout.addLayout(group_layout)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton(T("OK"))
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton(T("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def get_decision(self) -> str:
        id = self.group.checkedId()
        return {1: "overwrite", 2: "skip", 3: "rename"}.get(id, "overwrite")
