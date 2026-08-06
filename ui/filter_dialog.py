import json
import threading
import time
import traceback
from typing import Optional
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QComboBox, QLineEdit, QPushButton,
    QRadioButton, QButtonGroup, QScrollArea, QWidget,
    QFrame, QMessageBox, QProgressDialog, QApplication,
    QCalendarWidget, QTimeEdit
)
from PySide6.QtCore import Qt, QDate, QTime, QLocale

from core.filter_engine import (
    FilterRule, FilterPreset,
    load_preset, save_preset, match,
)
from core.scanner import scan_full
from core.logger import log_match, log_info, log_error, log, safe
from core.config import is_pro
from core.i18n import T
from ui.tree_widget import FileTreeWidget
from ui.preview_dialog import PreviewDialog

FREE_MAX_RULES = 2


class _Cancelled(Exception):
    pass


FIELD_OPTS = {
    "name":      ["contains", "not_contains", "equals", "starts_with", "ends_with", "regex"],
    "extension": ["is", "is_not", "is_one_of"],
    "path":      ["contains", "not_contains"],
    "size":      ["gt", "lt", "between"],
    "date":      ["before", "after", "between", "last_n_days"],
    "hidden":    ["is"],
}

FIELD_LABELS = {
    "name":      T("Name"), "extension": T("Extension"), "path": T("Path"),
    "size":      T("Size"), "date": T("Date"), "hidden": T("Hidden"),
}

OP_LABELS = {
    "contains": T("contains"), "not_contains": T("not contains"),
    "equals": T("equals"), "starts_with": T("starts with"),
    "ends_with": T("ends with"), "regex": T("regex"),
    "is": T("is"), "is_not": T("is not"), "is_one_of": T("is one of"),
    "gt": T("greater than"), "lt": T("less than"), "between": T("between"),
    "before": T("before"), "after": T("after"), "last_n_days": T("last N days"),
}


class _RuleRow(QFrame):
    """A single row in the filter editor."""
    def __init__(self, parent_dialog, rule: FilterRule = None):
        super().__init__()
        self._dialog = parent_dialog
        self.setFrameStyle(QFrame.StyledPanel)
        self._sys_fmt = QLocale.system().dateFormat(QLocale.ShortFormat)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.cb_enabled = QCheckBox()
        self.cb_enabled.setToolTip(T("toggle rule"))
        self.cb_enabled.setChecked(rule.enabled if rule else False)
        layout.addWidget(self.cb_enabled)

        self.cb_field = QComboBox()
        for key, label in FIELD_LABELS.items():
            self.cb_field.addItem(label, key)
        if rule:
            self.cb_field.setCurrentIndex(
                list(FIELD_LABELS.keys()).index(rule.field)
            )
        layout.addWidget(self.cb_field)

        self.cb_op = QComboBox()
        self._load_ops(self.cb_field.currentData())
        if rule:
            idx = self.cb_op.findData(rule.operator)
            if idx >= 0:
                self.cb_op.setCurrentIndex(idx)
        layout.addWidget(self.cb_op)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText(T("value..."))
        layout.addWidget(self.value_input, 1)

        self.value_min = QLineEdit()
        self.value_min.setPlaceholderText(T("minimum (e.g: 100)"))
        layout.addWidget(self.value_min, 1)

        self.btn_calendar = QPushButton("📅")
        self.btn_calendar.setFixedWidth(34)
        self.btn_calendar.setToolTip(T("Pick start date"))
        self.btn_calendar.clicked.connect(lambda: self._pick_date("min"))
        self.btn_calendar.setVisible(False)
        layout.addWidget(self.btn_calendar)

        self.value_max = QLineEdit()
        self.value_max.setPlaceholderText(T("maximum (e.g: 2000)"))
        layout.addWidget(self.value_max, 1)

        self.btn_calendar2 = QPushButton("📅")
        self.btn_calendar2.setFixedWidth(34)
        self.btn_calendar2.setToolTip(T("Pick end date"))
        self.btn_calendar2.clicked.connect(lambda: self._pick_date("max"))
        self.btn_calendar2.setVisible(False)
        layout.addWidget(self.btn_calendar2)

        # Unit selector for size
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("B", "b")
        self.unit_combo.addItem("KB", "kb")
        self.unit_combo.addItem("MB", "mb")
        self.unit_combo.addItem("GB", "gb")
        self.unit_combo.setToolTip(T("Unit of the entered value"))
        self.unit_combo.setVisible(False)
        layout.addWidget(self.unit_combo)

        # Extra hint for date range / days
        self.date_hint = QLabel("")
        self.date_hint.setStyleSheet("color: gray;")
        self.date_hint.setVisible(False)
        layout.addWidget(self.date_hint)

        # Time editor for date (before/after)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.timeChanged.connect(self._on_time_changed)
        self.time_edit.setVisible(False)
        layout.addWidget(self.time_edit)

        self.cb_scan_all = QCheckBox(T("ScanAll"))
        self.cb_scan_all.setToolTip(T("Search the entire source folder"))
        self.cb_scan_all.setChecked(rule.scan_all if rule else False)
        layout.addWidget(self.cb_scan_all)

        btn_del = QPushButton("X")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(self._delete_me)
        layout.addWidget(btn_del)

        # Load value (convert stored format -> display format)
        if rule:
            if rule.field == "size":
                if rule.operator == "between":
                    mi, ma, unit = self._split_size_range(rule.value)
                    self.value_min.setText(mi)
                    self.value_max.setText(ma)
                    idx = self.unit_combo.findData(unit)
                    if idx >= 0:
                        self.unit_combo.setCurrentIndex(idx)
                else:
                    num, unit = self._split_size_value(rule.value)
                    self.value_input.setText(num)
                    idx = self.unit_combo.findData(unit)
                    if idx >= 0:
                        self.unit_combo.setCurrentIndex(idx)
            elif rule.field == "date":
                if rule.operator == "between":
                    if "," in rule.value:
                        mi, ma = rule.value.split(",", 1)
                    else:
                        mi, ma = rule.value, ""
                    self.value_min.setText(self._iso_to_display(mi))
                    self.value_max.setText(self._iso_to_display(ma))
                else:
                    self.value_input.setText(self._iso_to_display(rule.value))
            else:
                self.value_input.setText(rule.value)

        self.value_min.setVisible(False)
        self.value_max.setVisible(False)
        self._update_aux_visibility()

        self._prev_op = self.cb_op.currentData()

        # Connect after all widgets exist so signals don't fire mid-init
        self.cb_field.currentIndexChanged.connect(self._on_field_changed)
        self.cb_op.currentIndexChanged.connect(self._on_op_changed)

    # ── helpers ────────────────────────────────────────────

    def _on_field_changed(self):
        field = self.cb_field.currentData()
        self._load_ops(field)
        self._prev_op = self.cb_op.currentData()
        self._reset_value()
        self._update_aux_visibility()

    def _on_op_changed(self):
        new_op = self.cb_op.currentData()
        self._transfer_values(new_op)
        self._prev_op = new_op
        self._update_aux_visibility()

    def _transfer_values(self, new_op):
        """Al cambiar de operador dentro del mismo campo se conserva el valor.
        Al elegir 'entre' el valor actual pasa al primer casillero; al salir
        de 'entre' el primer casillero vuelve al valor simple."""
        field = self.cb_field.currentData()
        prev = self._prev_op
        if prev is None or prev == new_op or field not in ("size", "date"):
            return
        if new_op == "between":
            cur = self.value_input.text().strip()
            if cur and not self.value_min.text().strip():
                self.value_min.setText(cur)
                self.value_input.clear()
        elif prev == "between":
            v = self.value_min.text().strip() or self.value_max.text().strip()
            if v and not self.value_input.text().strip():
                self.value_input.setText(v)
                self.value_min.clear()
                self.value_max.clear()

    def _reset_value(self):
        self.value_input.clear()
        self.value_min.clear()
        self.value_max.clear()
        self.unit_combo.setCurrentIndex(0)
        self.time_edit.setTime(QTime(0, 0))

    def _load_ops(self, field):
        self.cb_op.blockSignals(True)
        self.cb_op.clear()
        for op in FIELD_OPTS.get(field, ["contains"]):
            self.cb_op.addItem(OP_LABELS.get(op, op), op)
        self.cb_op.blockSignals(False)

    def _update_aux_visibility(self):
        field = self.cb_field.currentData()
        op = self.cb_op.currentData()

        self.value_input.setVisible(False)
        self.value_min.setVisible(False)
        self.value_max.setVisible(False)
        self.unit_combo.setVisible(False)
        self.date_hint.setVisible(False)
        self.btn_calendar.setVisible(False)
        self.btn_calendar2.setVisible(False)
        self.time_edit.setVisible(False)

        if field == "size":
            self.unit_combo.setVisible(True)
            if op == "between":
                self.value_min.setVisible(True)
                self.value_max.setVisible(True)
                self.value_min.setPlaceholderText(T("minimum (e.g: 100)"))
                self.value_max.setPlaceholderText(T("maximum (e.g: 2000)"))
                self.value_min.setToolTip(T("minimum size tooltip"))
                self.value_max.setToolTip(T("maximum size tooltip"))
            else:
                self.value_input.setVisible(True)
                self.value_input.setPlaceholderText("ej: 500")
                self.value_input.setToolTip(T("numeric value tooltip"))
        elif field == "date":
            if op == "last_n_days":
                self.value_input.setVisible(True)
                self.value_input.setPlaceholderText(T("e.g: 7"))
                self.value_input.setToolTip(T("days ago tooltip"))
                self.date_hint.setVisible(True)
                self.date_hint.setText(T("Number of days"))
            elif op == "between":
                self.value_min.setVisible(True)
                self.value_max.setVisible(True)
                self.btn_calendar.setVisible(True)
                self.btn_calendar2.setVisible(True)
                self.value_min.setPlaceholderText(T("start date placeholder", fmt=self._sys_fmt))
                self.value_max.setPlaceholderText(T("end date placeholder", fmt=self._sys_fmt))
                self.value_min.setToolTip(T("start date tooltip", fmt=self._sys_fmt))
                self.value_max.setToolTip(T("end date tooltip", fmt=self._sys_fmt))
            else:  # before / after
                self.value_input.setVisible(True)
                self.btn_calendar.setVisible(True)
                self.time_edit.setVisible(True)
                self.value_input.setPlaceholderText(T("before date placeholder", fmt=self._sys_fmt))
                self.value_input.setToolTip(T("date format tooltip", fmt=self._sys_fmt))
        elif field == "name":
            self.value_input.setVisible(True)
            ex = {
                "contains": T("e.g: informe"),
                "not_contains": T("e.g: secret"),
                "equals": T("e.g: budget"),
                "starts_with": T("e.g: invoice_"),
                "ends_with": T("e.g: final"),
                "regex": T("e.g: ^doc[0-9]+$"),
            }
            self.value_input.setPlaceholderText(ex.get(op, T("e.g: informe")))
            self.value_input.setToolTip(T("name without ext tooltip"))
        elif field == "extension":
            self.value_input.setVisible(True)
            ex = {"is": T("e.g: .pdf"), "is_not": T("e.g: .exe"), "is_one_of": T("e.g: .jpg,.png")}
            self.value_input.setPlaceholderText(ex.get(op, T("e.g: .pdf")))
            self.value_input.setToolTip(T("extension only tooltip"))
        elif field == "path":
            self.value_input.setVisible(True)
            ex = {"contains": T("e.g: photos/2024"), "not_contains": T("e.g: temp")}
            self.value_input.setPlaceholderText(ex.get(op, T("e.g: photos/2024")))
            self.value_input.setToolTip(T("path relative tooltip"))
        else:  # hidden
            self.value_input.setVisible(True)
            self.value_input.setPlaceholderText(T("yes / no"))
            self.value_input.setToolTip(T("Write 'yes' for hidden or 'no'"))

    # ── size value ─────────────────────────────────────────

    @staticmethod
    def _split_size_value(value: str):
        v = value.strip().lower()
        parts = v.split(",")
        if not parts or not parts[0].strip():
            return "", "b"
        last = parts[-1].strip()
        unit = "b"
        for u in ("gb", "mb", "kb", "b"):
            if last.endswith(u):
                unit = u
                break
        nums = []
        for p in parts:
            p = p.strip()
            for u in ("gb", "mb", "kb", "b"):
                if p.endswith(u):
                    p = p[: -len(u)].strip()
                    break
            nums.append(p)
        num = ",".join(nums) if len(parts) > 1 else (nums[0] if nums else "")
        return num, unit

    @staticmethod
    def _split_size_range(value: str):
        parts = [p.strip() for p in value.split(",")] if value else []
        if len(parts) < 2:
            parts = (parts + ["", ""])[:2]
        unit = "b"
        for p in parts:
            lp = p.lower()
            for u in ("gb", "mb", "kb", "b"):
                if lp.endswith(u):
                    unit = u
                    break
        clean = []
        for p in parts:
            lp = p.lower()
            for u in ("gb", "mb", "kb", "b"):
                if lp.endswith(u):
                    p = p[: -len(u)]
                    break
            clean.append(p.strip())
        return clean[0], clean[1], unit

    @staticmethod
    def _mk_size_value(num: str, unit: str) -> str:
        num = num.strip()
        if not num:
            return ""
        if unit == "b":
            return num
        return f"{num}{unit}"

    # ── date value conversion ──────────────────────────────

    def _display_to_iso(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if "," in text:
            parts = [self._display_to_iso(p) for p in text.split(",")]
            if any(p == "" for p in parts):
                return ""
            return ",".join(parts)
        pieces = text.split()
        d = QDate.fromString(pieces[0], self._sys_fmt) if pieces else QDate()
        if not d.isValid():
            return ""
        iso = d.toString("yyyy-MM-dd")
        if len(pieces) > 1:
            t = QTime.fromString(pieces[1], "HH:mm")
            if t.isValid():
                iso += " " + t.toString("HH:mm")
        return iso

    def _iso_to_display(self, iso: str) -> str:
        iso = iso.strip()
        if not iso:
            return ""
        if "," in iso:
            return ",".join(self._iso_to_display(p) for p in iso.split(","))
        pieces = iso.split()
        d = QDate.fromString(pieces[0], "yyyy-MM-dd")
        if not d.isValid():
            return iso
        out = d.toString(self._sys_fmt)
        if len(pieces) > 1:
            out += " " + pieces[1]
        return out

    def _pick_date(self, target: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(T("Pick date"))
        lay = QVBoxLayout(dlg)
        cal = QCalendarWidget()
        lay.addWidget(cal)
        btn_ok = QPushButton(T("OK"))
        btn_ok.clicked.connect(dlg.accept)
        lay.addWidget(btn_ok)
        if dlg.exec() == QDialog.Accepted:
            self._insert_date(cal.selectedDate(), target)

    def _insert_date(self, qd: QDate, target: str = "min"):
        disp = qd.toString(self._sys_fmt)
        field = self.cb_field.currentData()
        op = self.cb_op.currentData()
        if field == "date" and op == "between":
            if target == "max":
                self.value_max.setText(disp)
            else:
                self.value_min.setText(disp)
        else:
            cur = self.value_input.text().strip()
            pieces = cur.split()
            time_part = pieces[1] if len(pieces) > 1 else ""
            self.value_input.setText(disp + (f" {time_part}" if time_part else ""))

    def _on_time_changed(self):
        if self.cb_field.currentData() != "date":
            return
        op = self.cb_op.currentData()
        if op not in ("before", "after"):
            return
        hm = self.time_edit.time().toString("HH:mm")
        cur = self.value_input.text().strip()
        pieces = cur.split()
        if len(pieces) > 1:
            pieces[1] = hm
            self.value_input.setText(" ".join(pieces))
        elif pieces:
            self.value_input.setText(pieces[0] + " " + hm)
        else:
            self.value_input.setText(hm)

    def _delete_me(self):
        self._dialog._remove_row(self)

    def to_rule(self) -> FilterRule:
        field = self.cb_field.currentData()
        op = self.cb_op.currentData()
        if field == "size":
            unit = self.unit_combo.currentData() or "b"
            if op == "between":
                mi = self._mk_size_value(self.value_min.text(), unit)
                ma = self._mk_size_value(self.value_max.text(), unit)
                value = f"{mi},{ma}" if (mi and ma) else ""
            else:
                value = self._mk_size_value(self.value_input.text(), unit)
        elif field == "date":
            if op == "between":
                mi = self._display_to_iso(self.value_min.text())
                ma = self._display_to_iso(self.value_max.text())
                value = f"{mi},{ma}" if (mi and ma) else ""
            else:
                value = self._display_to_iso(self.value_input.text())
        else:
            value = self.value_input.text().strip()
        return FilterRule(
            enabled=self.cb_enabled.isChecked(),
            scan_all=self.cb_scan_all.isChecked(),
            field=field,
            operator=op,
            value=value,
        )


class FilterDialog(QDialog):
    def __init__(self, tree_widget: FileTreeWidget, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Advanced filters"))
        self.setMinimumSize(750, 400)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._tree = tree_widget
        self._rows: list = []
        self._loading = False
        self._cached_preset_json: Optional[str] = None
        self._cached_matched: list = []
        self._scan_cancelled = False
        self._busy = False

        layout = QVBoxLayout(self)

        # Master toggle
        master_layout = QHBoxLayout()
        self.cb_master = QCheckBox(T("Filter active"))
        self.cb_master.setChecked(False)
        master_layout.addWidget(self.cb_master)
        master_layout.addStretch()
        layout.addLayout(master_layout)

        # AND / OR
        logic_layout = QHBoxLayout()
        logic_layout.addWidget(QLabel(T("Logic:")))
        self._logic_group = QButtonGroup(self)
        self.rb_and = QRadioButton(T("AND"))
        self.rb_or = QRadioButton(T("OR"))
        self._logic_group.addButton(self.rb_and, 1)
        self._logic_group.addButton(self.rb_or, 2)
        logic_layout.addWidget(self.rb_and)
        logic_layout.addWidget(self.rb_or)
        logic_layout.addStretch()
        layout.addLayout(logic_layout)

        # Scroll area for rules
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll, 1)

        # Add-rule row
        add_row = QHBoxLayout()
        btn_add = QPushButton(T("+ Add rule"))
        btn_add.clicked.connect(self._add_row)
        add_row.addWidget(btn_add)
        btn_clear = QPushButton(T("Clear all"))
        btn_clear.clicked.connect(self._clear_all)
        add_row.addWidget(btn_clear)
        add_row.addStretch()
        add_row.addStretch()
        layout.addLayout(add_row)

        # Count / preview / select / deselect / close
        self._count_label = QLabel(T("Press Preview to see matches"))
        layout.addWidget(self._count_label)

        btn_row = QHBoxLayout()
        btn_preview = QPushButton(T("Preview"))
        btn_preview.clicked.connect(self._preview)
        btn_row.addWidget(btn_preview)

        btn_select = QPushButton(T("Select"))
        btn_select.clicked.connect(lambda: self._apply(select=True))
        btn_row.addWidget(btn_select)

        btn_deselect = QPushButton(T("Deselect"))
        btn_deselect.clicked.connect(lambda: self._apply(select=False))
        btn_row.addWidget(btn_deselect)

        btn_row.addStretch()
        self.btn_close = QPushButton(T("Close"))
        self.btn_close.clicked.connect(self._close_and_save)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        # Load saved rules
        self._load_saved()

    def _load_saved(self):
        self._loading = True
        preset = load_preset()
        self.cb_master.setChecked(preset.enabled)
        self.rb_and.setChecked(preset.logic == "AND")
        self.rb_or.setChecked(preset.logic == "OR")
        for rule in preset.rules:
            self._add_row(rule)
        self._loading = False

    def _add_row(self, rule: FilterRule = None):
        if not self._loading and not is_pro() and len(self._rows) >= FREE_MAX_RULES:
            QMessageBox.information(
                self, T("Limit reached: {n} filters", n=FREE_MAX_RULES),
                T("Free limit: {n} filters. Activate Pro for unlimited.", n=FREE_MAX_RULES)
            )
            return
        row = _RuleRow(self, rule)
        self._rows.append(row)
        self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, row)
        self._update_add_button_state()

    def _update_add_button_state(self):
        from PySide6.QtWidgets import QPushButton as _PB
        for child in self.findChildren(_PB):
            if child.text() == "+ Agregar regla":
                limited = (not is_pro() and len(self._rows) >= FREE_MAX_RULES)
                child.setEnabled(not limited)
                if limited:
                    child.setToolTip(
                        T("Free limit: {n} filters. Activate Pro for unlimited.", n=FREE_MAX_RULES)
                    )
                else:
                    child.setToolTip("")

    def _remove_row(self, row):
        if row in self._rows:
            self._rows.remove(row)
            self._scroll_layout.removeWidget(row)
            row.deleteLater()
            self._update_add_button_state()

    def _clear_all(self):
        for row in list(self._rows):
            self._remove_row(row)

    def _current_preset(self) -> FilterPreset:
        return FilterPreset(
            enabled=self.cb_master.isChecked(),
            logic="AND" if self.rb_and.isChecked() else "OR",
            rules=[r.to_rule() for r in self._rows],
        )

    @staticmethod
    def _preset_json(preset) -> str:
        return json.dumps({"enabled": preset.enabled, "logic": preset.logic,
                           "rules": [(r.enabled, r.field, r.operator, r.value, r.scan_all)
                                     for r in preset.rules]}, sort_keys=True)

    def _get_matched_async(self, on_result):
        if self._busy:
            log_info("Operación ya en curso, ignorando click")
            return
        self._scan_cancelled = False

        preset = self._current_preset()
        if not preset.enabled:
            on_result([])
            return

        pj = self._preset_json(preset)
        if pj == self._cached_preset_json:
            log("Filtro: usando resultado en caché")
            on_result(self._cached_matched)
            return

        self._run_filtering(preset, on_result)

    def _run_filtering(self, preset, on_result):
        """Ejecuta scan+match en el hilo principal (estable). El progreso se
        actualiza con processEvents; Cancelar solo marca una flag que aborta."""
        need_full = any(r.scan_all for r in preset.rules if r.enabled)
        self._scan_cancelled = False
        self._busy = True
        self._set_buttons_enabled(False)
        self.btn_close.setEnabled(True)
        self._progress_start = time.time()

        if need_full and self._tree.root_path:
            progress = QProgressDialog(T("Scanning folders..."), T("Cancel"), 0, 0, self)
            progress.setWindowTitle(T("Scanning"))
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.canceled.connect(self._cancel_scan)
            progress.show()

            def cb(cur, total):
                if self._scan_cancelled:
                    raise _Cancelled
                self._update_progress(progress, cur, total, T("Scanning"))

            t0 = time.time()
            try:
                all_files = scan_full(self._tree.root_path, cb, preset=preset)
                result = match(preset, all_files, cb)
            except _Cancelled:
                progress.close()
                self._busy = False
                self._set_buttons_enabled(True)
                log("Filtro: operación cancelada por el usuario")
                return
            progress.close()
            self._busy = False
            self._set_buttons_enabled(True)
            log(f"Filtro: scan completo en {time.time() - t0:.1f}s -> {len(result)} coincidencias")
            log_match(len(preset.rules), len(all_files), len(result), time.time() - t0)
        else:
            all_files = self._tree.get_all_loaded_file_infos()
            log(f"Filtro: filtrando {len(all_files)} archivos del árbol")
            if not all_files:
                self._busy = False
                self._set_buttons_enabled(True)
                on_result([])
                return
            progress = QProgressDialog(T("Filtering..."), T("Cancel"), 0, len(all_files), self)
            progress.setWindowTitle(T("Filtering"))
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.canceled.connect(self._cancel_scan)
            progress.show()

            def cb(cur, total):
                if self._scan_cancelled:
                    raise _Cancelled
                self._update_progress(progress, cur, total, T("Filtering"))

            t0 = time.time()
            try:
                result = match(preset, all_files, cb)
            except _Cancelled:
                progress.close()
                self._busy = False
                self._set_buttons_enabled(True)
                log("Filtro: operación cancelada por el usuario")
                return
            progress.close()
            self._busy = False
            self._set_buttons_enabled(True)
            log_match(len(preset.rules), len(all_files), len(result), time.time() - t0)

        self._cached_preset_json = self._preset_json(preset)
        self._cached_matched = result
        on_result(result)

    def _update_progress(self, progress, cur, total, phase):
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(cur)
        elapsed = time.time() - getattr(self, "_progress_start", time.time())
        progress.setLabelText(f"{phase}... {cur:,} elementos · {elapsed:.0f}s")
        QApplication.processEvents()

    def _cancel_scan(self):
        if self._busy:
            log("Filtro: cancelación solicitada")
            self._scan_cancelled = True

    def _set_buttons_enabled(self, enabled: bool):
        for child in self.findChildren(QPushButton):
            child.setEnabled(enabled)

    @safe
    def _preview(self):
        log("Filtro: Previsualizar clickeado")
        self._get_matched_async(self._on_preview_result)

    def _on_preview_result(self, matched):
        log(f"Filtro: preview con {len(matched)} resultados")
        if not matched:
            QMessageBox.information(self, T("Preview"), T("No matching files."))
            return
        dlg = PreviewDialog(matched, self._tree, self)
        dlg.exec()

    @safe
    def _apply(self, select: bool):
        log(f"Filtro: {'Seleccionar' if select else 'Deseleccionar'} clickeado")
        self._apply_select = select
        self._get_matched_async(self._on_apply_result)

    @safe
    def _on_apply_result(self, matched):
        log(f"Filtro: aplicar a {len(matched)} archivos")
        if not matched:
            QMessageBox.information(self, T("Apply"), T("No matching files."))
            return

        cancel_flag = threading.Event()
        progress = QProgressDialog(T("Applying selection..."), T("Cancel"), 0, len(matched), self)
        progress.setWindowTitle(T("Applying"))
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(lambda: cancel_flag.set())
        progress.show()

        def _cb(cur, total):
            progress.setValue(cur)
            progress.setLabelText(f"{T('Applying')}... {cur:,} / {total:,}")

        self._tree.batch_check_files(matched, self._apply_select, _cb, cancel_flag)
        progress.close()

    @safe
    def _close_and_save(self):
        save_preset(self._current_preset())
        log("Filtro: cerrado y preset guardado")
        self.accept()
