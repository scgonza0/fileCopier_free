from pathlib import Path
from typing import List, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileIconProvider
)
from PySide6.QtCore import Qt
from core.models import FileInfo
from core.copier import format_size
from core.i18n import T


class SummaryDialog(QDialog):
    def __init__(self, files: List[FileInfo], source_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Summary - Selected files"))
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(T("Total: {n} files selected", n=len(files))))

        tree = QTreeWidget()
        tree.setHeaderLabels([T("Name"), T("Size"), T("Modified")])
        tree.setColumnWidth(0, 350)
        tree.setColumnWidth(1, 100)
        tree.setColumnWidth(2, 150)
        tree.setRootIsDecorated(True)
        tree.setAlternatingRowColors(True)
        tree.setIndentation(20)

        ip = QFileIconProvider()
        folder_icon = ip.icon(QFileIconProvider.Folder)
        file_icon = ip.icon(QFileIconProvider.File)

        items: Dict[str, QTreeWidgetItem] = {}

        sorted_files = sorted(files, key=lambda f: f.relative_path)

        for fi in sorted_files:
            parts = fi.relative_path.split("/")
            parent_item = None
            path_so_far = ""

            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    item = QTreeWidgetItem()
                    item.setIcon(0, file_icon)
                    item.setText(0, part)
                    item.setText(1, format_size(fi.size))
                    item.setText(2, fi.modified.strftime("%Y-%m-%d %H:%M"))
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Checked)
                else:
                    path_so_far = f"{path_so_far}/{part}" if path_so_far else part
                    if path_so_far not in items:
                        dir_item = QTreeWidgetItem()
                        dir_item.setIcon(0, folder_icon)
                        dir_item.setText(0, part)
                        dir_item.setFlags(dir_item.flags() | Qt.ItemIsUserCheckable)
                        dir_item.setCheckState(0, Qt.Checked)
                        items[path_so_far] = dir_item
                    else:
                        dir_item = items[path_so_far]
                    parent_item = dir_item

                if parent_item is not None and i == len(parts) - 1:
                    if isinstance(parent_item, QTreeWidgetItem):
                        parent_item.addChild(item)
                    else:
                        tree.addTopLevelItem(item)
                elif i == 0 and len(parts) == 1:
                    tree.addTopLevelItem(item)

        # Insert items into tree properly
        for path_so_far, dir_item in items.items():
            parent_path = str(Path(path_so_far).parent).replace("\\", "/")
            if parent_path == "." or parent_path not in items:
                tree.addTopLevelItem(dir_item)
            else:
                items[parent_path].addChild(dir_item)

        tree.expandAll()
        layout.addWidget(tree)

        btn = QPushButton(T("Close"))
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
