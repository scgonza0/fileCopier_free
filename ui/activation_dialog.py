from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)
from PySide6.QtCore import Qt
from core.i18n import T
from core.config import get_license_state, set_license, is_pro
from core.logger import log, log_error
from core.version import APP_NAME, APP_VERSION, CONTACT_EMAIL
from core.machine import machine_display


class ActivationDialog(QDialog):
    """Activa la versión Pro pegando una licencia firmada.

    Si la licencia está atada a una PC (campo `machine`), sólo es válida en la
    computadora para la que se emitió.  En la edición gratuita muestra el
    código de PC local para que el usuario lo copie y envíe al desarrollador
    al momento de comprar.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Activate Pro license"))
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)

        state = get_license_state()
        if state.get("pro"):
            name = state.get("name", "")
            email = state.get("email", "")
            expires = state.get("expires", "") or T("Lifetime")
            layout.addWidget(QLabel(T("License state: {state}", state=T("PRO activated"))))
            layout.addWidget(QLabel(T("Licensee: {name} ({email})", name=name, email=email)))
            layout.addWidget(QLabel(T("Validity: {expires}", expires=expires)))
            btn_disable = QPushButton(T("Deactivate Pro on this PC"))
            btn_disable.clicked.connect(self._deactivate)
            layout.addWidget(btn_disable)
            btn_close = QPushButton(T("Close"))
            btn_close.clicked.connect(self.accept)
            layout.addWidget(btn_close)
            return

        # ── edición gratuita: instrucciones + código de PC ────────────────
        layout.addWidget(QLabel(T("{app_name} {version} — free version",
                                  app_name=APP_NAME, version=APP_VERSION)))
        layout.addWidget(QLabel(T("free_intro")))

        # Código de PC local (lo copia el usuario para enviarlo al comprar)
        machine_id = machine_display()
        ml = QHBoxLayout()
        ml.addWidget(QLabel("<b>" + T("Your PC code") + "</b>"))
        code_edit = QLineEdit(machine_id)
        code_edit.setReadOnly(True)
        code_edit.setToolTip(T("PC code tooltip", email=CONTACT_EMAIL))
        btn_copy_pc = QPushButton(T("Copy PC code"))
        btn_copy_pc.setToolTip(T("Copy PC code to send it by email when buying Pro"))
        ml.addWidget(code_edit)
        ml.addWidget(btn_copy_pc)
        layout.addLayout(ml)

        btn_copy_pc.clicked.connect(lambda: self._copy_to_clipboard(
            machine_id, "Código de PC copiado al portapapeles"))

        layout.addWidget(QLabel(T("Buyed and received the license? Paste it below.")))
        self.input = QLineEdit()
        self.input.setPlaceholderText(T("Placeholder example"))
        self.input.setMinimumHeight(64)
        layout.addWidget(self.input)

        row = QHBoxLayout()
        btn_activate = QPushButton(T("Verify and activate"))
        btn_activate.clicked.connect(self._activate)
        row.addWidget(btn_activate)
        row.addStretch()
        btn_cancel = QPushButton(T("Close"))
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)
        layout.addLayout(row)

    def _copy_to_clipboard(self, text: str, msg: str):
        try:
            cb = QApplication.clipboard()
            cb.setText(text)
            QMessageBox.information(self, T("Copied"), msg)
        except Exception as e:
            log_error(f"No se pudo copiar al portapapeles: {e}")

    def _activate(self):
        try:
            from licensing.verify import verify_key
        except ImportError:
            QMessageBox.information(self, T("Not available"),
                                    T("This edition has no Pro activation."))
            return

        key = self.input.text().strip()
        if not key:
            QMessageBox.warning(self, T("Invalid license"), T("Enter the license in the field."))
            return

        data = verify_key(key)
        if data is None:
            # ¿firma válida pero atada a otra PC? (permite diagóstico UX)
            try:
                other = verify_key(key, check_machine=False)
            except Exception:
                other = None
            if other is not None:
                QMessageBox.critical(
                    self, T("Valid license, but for another device"),
                    T("The license signature is valid, but it is bound to\nanother device.\n\nLicenses are per device (USD 10 each). If you need to move it to\nthis machine, send your PC code ({code}) to {email}.",
                      code=machine_display(), email=CONTACT_EMAIL)
                )
                return
            QMessageBox.critical(
                self, T("Invalid license"),
                T("The license is invalid, expired or corrupt.\nCheck you pasted it complete and without errors.")
            )
            return

        set_license(True, key=key, name=data.get("name", ""),
                    email=data.get("email", ""),
                    machine=data.get("machine", ""),
                    expires=data.get("expires", ""))
        log(f"Licencia Pro activada para {data.get('name')} <{data.get('email')}>")
        QMessageBox.information(
            self, T("Pro activated"),
            T("Thank you, {name}! Pro is now activated on\nthis PC. Limits are now lifted.", name=data.get("name", ""))
        )
        self.accept()

    def _deactivate(self):
        from core.config import clear_license
        clear_license()
        log("Licencia Pro desactivada por el usuario")
        QMessageBox.information(self, T("Pro deactivated"), T("Pro has been deactivated on this PC."))
        self.accept()

    @staticmethod
    def _contact_email() -> str:
        return CONTACT_EMAIL


def show_activation(parent=None) -> bool:
    """Abre el dialog de activación. Devuelve True si quedó activada la Pro."""
    before = is_pro()
    dlg = ActivationDialog(parent)
    dlg.exec()
    return is_pro() and not before
