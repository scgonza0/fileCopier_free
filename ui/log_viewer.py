from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt
from core.i18n import T
from core.logger import get_log_path


class LogViewer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Application log"))
        self.setMinimumSize(850, 600)

        layout = QVBoxLayout(self)

        self.label = QLabel("")
        layout.addWidget(self.label)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.text, 1)

        row = QHBoxLayout()
        btn_refresh = QPushButton(T("Refresh"))
        btn_refresh.clicked.connect(self.refresh)
        row.addWidget(btn_refresh)
        row.addStretch()
        btn_close = QPushButton(T("Close"))
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self.refresh()

    def refresh(self):
        path = get_log_path()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            content = T("Error reading the log:\n{e}", e=e)
        self.text.setPlainText(content)
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.label.setText(T("File: {path}", path=path))
