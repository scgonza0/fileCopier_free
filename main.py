import sys
import traceback

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType

from core.logger import init_log, log, log_error, log_exception
from ui.main_window import MainWindow


def _excepthook(exc_type, exc, tb):
    log_error(f"EXCEPCION NO CAPTURADA: {exc_type.__name__}: {exc}\n{traceback.format_exception(exc_type, exc, tb)}")
    # Mantener el comportamiento por defecto en desarrollo (imprime en stderr)
    sys.__excepthook__(exc_type, exc, tb)


_QT_LEVELS = {
    QtMsgType.QtDebugMsg: "DBG",
    QtMsgType.QtInfoMsg: "INF",
    QtMsgType.QtWarningMsg: "WRN",
    QtMsgType.QtCriticalMsg: "CRIT",
    QtMsgType.QtFatalMsg: "FATAL",
}


def _qt_message_handler(mode, context, message):
    lvl = _QT_LEVELS.get(mode, "QT?")
    file = context.file or "?"
    line = context.line or 0
    log_error(f"[QT-{lvl}] {file}:{line} {message}")


def main():
    try:
        init_log()
        log("--- INICIO ---")
        log(f"Python {sys.version.split()[0]} | frozen: {getattr(sys, 'frozen', False)}")
        log(f"argv={sys.argv}")

        # Hooks globales para capturar cualquier crash
        sys.excepthook = _excepthook
        qInstallMessageHandler(_qt_message_handler)
        log("Hooks de excepción instalados")

        # Migración única de la config vieja (raíz del proyecto) a %APPDATA%
        from core.config import migrate_legacy_config
        migrate_legacy_config()

        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        log("QApplication creado")

        window = MainWindow()
        window.show()
        log("Ventana principal mostrada")

        _maybe_ask_delete_old_log()

        rc = app.exec()
        log(f"app.exec() terminó con código {rc}")
        sys.exit(rc)
    except Exception as e:
        log_error(f"main() CRASH: {e}\n{traceback.format_exc()}")
        raise


def _maybe_ask_delete_old_log():
    """Si el log tiene más de 15 días, pregunta si quiere borrarse."""
    try:
        from PySide6.QtWidgets import QMessageBox
        from core.logger import log_age_days, delete_log, log

        days = log_age_days()
        if days is None or days < 15:
            return
        reply = QMessageBox.question(
            None, "Log de la aplicación",
            f"El log de la aplicación tiene {int(days)} días.\n"
            "¿Querés borrarlo para liberar espacio?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_log()
            log("Log eliminado por el usuario")
    except Exception:
        pass


if __name__ == "__main__":
    main()
