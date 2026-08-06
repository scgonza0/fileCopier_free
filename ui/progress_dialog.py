from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QListWidget, QListWidgetItem, QPushButton
)
from PySide6.QtCore import Qt, QThread
from typing import List
from core.i18n import T


class ProgressDialog(QDialog):
    def __init__(self, worker, thread: QThread, total: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Copying files..."))
        self.setMinimumSize(500, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        self.label = QLabel(T("Copying {current} of {total} files...", current=0, total=total))
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setMaximum(total)
        layout.addWidget(self.progress)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.btn_close = QPushButton(T("Close"))
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self._ok_count = 0
        self._err_count = 0

        self._total = total

        worker.progress.connect(self._on_progress)
        worker.file_copied.connect(self._on_file_copied)
        worker.finished.connect(self._on_finished)

    def _on_progress(self, current: int, total: int):
        self.progress.setValue(current)
        self.label.setText(T("Copying {current} of {total} files...", current=current, total=total))

    def _on_file_copied(self, source: str, success: bool, error: str):
        name = source.split("\\")[-1] if "\\" in source else source.split("/")[-1]
        if success:
            self._ok_count += 1
            status = "✅"
            if error:
                text = f"{status} {name} - {error}"
            else:
                text = f"{status} {name}"
        else:
            self._err_count += 1
            text = f"❌ {name} - {error}"

        item = QListWidgetItem(text)
        self.list_widget.addItem(item)
        self.list_widget.scrollToBottom()

    def _on_finished(self):
        self.label.setText(
            T("completed: {ok} ok, {err} errors.", ok=self._ok_count, err=self._err_count)
        )
        self.btn_close.setEnabled(True)
