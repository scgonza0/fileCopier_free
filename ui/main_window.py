import time
from pathlib import Path
from typing import Optional, List

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt, QThread

from core.copier import (
    CopyWorker, check_conflicts, find_duplicate_names, format_size,
    build_flat_rename_map,
)
from core.config import is_pro
from core.i18n import T
from core.version import APP_NAME, APP_VERSION, PRO_PRICE_USD, CONTACT_EMAIL
from core.logger import log_copy, log_info, log_error, log, safe
from ui.tree_widget import FileTreeWidget
from ui.progress_dialog import ProgressDialog
from ui.conflict_dialog import ConflictDialog
from ui.summary_dialog import SummaryDialog
from ui.filter_dialog import FilterDialog
from ui.copy_options_dialog import CopyOptionsDialog
from ui.multi_dest_dialog import MultiDestDialog
from ui.log_viewer import LogViewer

FREE_MAX_FILES = 100


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(T("FileCopier - Selective Copy"))
        self.setMinimumSize(900, 650)
        # Icono de ventana (barra de titulo / taskbar cuando corre)
        from pathlib import Path
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "filecopier.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.source_path: Optional[Path] = None
        self.dest_path: Optional[Path] = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- Source / Destination ---
        path_group = QGroupBox(T("Source and Destination"))
        path_layout = QVBoxLayout(path_group)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel(T("Source:")))
        self.src_input = QLineEdit()
        self.src_input.setPlaceholderText("E:\\carpeta1\\carpeta2\\carpeta_de_origen"
                                          if T("Source:")=="Origen:" else "E:\\folder1\\folder2\\source folder")
        src_row.addWidget(self.src_input)
        self.btn_src = QPushButton(T("Browse"))
        self.btn_src.setToolTip(T("Browse source tooltip"))
        self.btn_src.clicked.connect(self._browse_source)
        src_row.addWidget(self.btn_src)
        path_layout.addLayout(src_row)

        dst_row = QHBoxLayout()
        dst_row.addWidget(QLabel(T("Destination:")))
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("X:\\CarpetaA\\carpeta_de_destino" if T("Source:")=="Origen:" else "X:\\FolderA\\destination folder")
        dst_row.addWidget(self.dst_input)
        self.btn_dst = QPushButton(T("Browse"))
        self.btn_dst.setToolTip(T("Browse dest tooltip"))
        self.btn_dst.clicked.connect(self._browse_dest)
        dst_row.addWidget(self.btn_dst)
        path_layout.addLayout(dst_row)

        main_layout.addWidget(path_group)

        # --- Filters ---
        filter_group = QGroupBox(T("Filters"))
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel(T("Show only (extensions):")))
        self.filter_show = QLineEdit()
        self.filter_show.setToolTip(T("Show only tooltip"))
        self.filter_show.setPlaceholderText(".txt,.py,.pdf")
        filter_layout.addWidget(self.filter_show)

        filter_layout.addWidget(QLabel(T("Hide (keywords):")))
        self.filter_hide = QLineEdit()
        self.filter_hide.setToolTip(T("Hide tooltip"))
        self.filter_hide.setPlaceholderText("__pycache__,temp,.git")
        filter_layout.addWidget(self.filter_hide)

        self.btn_apply_filters = QPushButton(T("Apply filters"))
        self.btn_apply_filters.setToolTip(T("Apply filters tooltip"))
        self.btn_apply_filters.clicked.connect(self._apply_filters)
        filter_layout.addWidget(self.btn_apply_filters)

        main_layout.addWidget(filter_group)

        # --- Tree ---
        self.tree = FileTreeWidget()
        main_layout.addWidget(self.tree, 1)

        self.status_label = QLabel(T("Selected: {n} · Size: {size} · Files: {files} · Folders: {folders}", n=0, size="0 B", files=0, folders=0))
        self.edition_label = QLabel(T("Free"))
        self.edition_label.setStyleSheet(
            "padding: 2px 12px; border-radius: 9px; color: white;"
        )
        self._refresh_edition_style()
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.edition_label)
        main_layout.addLayout(status_row)
        self.tree.selection_changed.connect(self._update_status)

        # --- Bottom actions ---
        action_layout = QHBoxLayout()

        self.btn_check_all = QPushButton(T("Select all"))
        self.btn_check_all.clicked.connect(lambda: self._check_all(True))
        action_layout.addWidget(self.btn_check_all)

        self.btn_uncheck_all = QPushButton(T("Deselect all"))
        self.btn_uncheck_all.clicked.connect(lambda: self._check_all(False))
        action_layout.addWidget(self.btn_uncheck_all)

        action_layout.addStretch()

        self.btn_scan = QPushButton(T("Load tree"))
        self.btn_scan.setToolTip(T("Load tree tooltip"))
        self.btn_scan.clicked.connect(self._load_tree)
        action_layout.addWidget(self.btn_scan)

        self.btn_summary = QPushButton(T("View summary"))
        self.btn_summary.setToolTip(T("View summary tooltip"))
        self.btn_summary.clicked.connect(self._show_summary)
        self.btn_summary.setEnabled(False)
        action_layout.addWidget(self.btn_summary)

        self.btn_adv_filters = QPushButton(T("Advanced filters"))
        self.btn_adv_filters.setToolTip(T("Advanced filters tooltip"))
        self.btn_adv_filters.clicked.connect(self._open_adv_filters)
        self.btn_adv_filters.setEnabled(False)
        action_layout.addWidget(self.btn_adv_filters)

        self.btn_copy = QPushButton(T("Copy selected files"))
        self.btn_copy.setToolTip(T("Copy tooltip"))
        self.btn_copy.clicked.connect(self._start_copy)
        self.btn_copy.setEnabled(False)
        action_layout.addWidget(self.btn_copy)

        self.btn_multi = QPushButton(T("Copy to multiple destinations"))
        self.btn_multi.setToolTip(T("Copy multi tooltip"))
        self.btn_multi.clicked.connect(self._start_multi_copy)
        self.btn_multi.setEnabled(False)
        action_layout.addWidget(self.btn_multi)

        self.btn_log = QPushButton(T("View log"))
        self.btn_log.setToolTip(T("View log tooltip"))
        self.btn_log.clicked.connect(self._open_log)
        action_layout.addWidget(self.btn_log)

        main_layout.addLayout(action_layout)

        self._build_menu()

    # ─── Menú / edición ─────────────────────────────────────

    def _build_menu(self):
        from PySide6.QtWidgets import QMenuBar

        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        m_file = menubar.addMenu(T("File"))
        act_exit = m_file.addAction(T("Exit"))
        act_exit.triggered.connect(self.close)

        m_pro = menubar.addMenu(T("Pro menu"))
        self.act_activate = m_pro.addAction(T("Activate Pro license..."))
        self.act_activate.triggered.connect(self._open_activation)
        m_pro.addSeparator()
        act_info = m_pro.addAction(T("What's included in Pro?"))
        act_info.triggered.connect(self._show_pro_info)

        m_help = menubar.addMenu(T("Help"))
        act_updates = m_help.addAction(T("Check for updates..."))
        act_updates.triggered.connect(self._check_updates)
        act_log = m_help.addAction(T("View log"))
        act_log.triggered.connect(self._open_log)
        act_tut = m_help.addAction(T("View usage tutorial"))
        act_tut.triggered.connect(self._view_tutorial)
        m_help.addSeparator()
        act_about = m_help.addAction(T("About"))
        act_about.triggered.connect(self._show_about)

    def _refresh_edition_style(self):
        if is_pro():
            self.edition_label.setText(T("PRO"))
            self.edition_label.setStyleSheet(
                "padding: 2px 12px; border-radius: 9px; color: white;"
                "background-color: #2e7d32;"
            )
            self.edition_label.setToolTip(T("Pro activated — no limits"))
        else:
            self.edition_label.setText(T("Free"))
            self.edition_label.setStyleSheet(
                "padding: 2px 12px; border-radius: 9px; color: white;"
                "background-color: #757575;"
            )
            self.edition_label.setToolTip(T("Free version (max 2 filters and 100 files per copy).\nActivate Pro from the Pro menu → Activate Pro license..."))

    @safe
    def _open_activation(self):
        from ui.activation_dialog import ActivationDialog
        before = is_pro()
        dlg = ActivationDialog(self)
        dlg.exec()
        if is_pro() and not before:
            self._refresh_edition_style()
        elif is_pro():
            self._refresh_edition_style()

    @safe
    def _show_pro_info(self):
        QMessageBox.information(
            self, T("What's included in Pro?"),
            T("pro_info", price=PRO_PRICE_USD, email=CONTACT_EMAIL),
          )

    @safe
    def _show_about(self):
        from core.logger import log_path

    def _view_tutorial(self):
        from core.i18n import current_language
        from pathlib import Path
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        here = Path(__file__).resolve().parent.parent
        docs = here / "docs"
        lang = current_language()
        html = docs / ("tutorial_%s.html" % lang)
        if not html.exists():
            html = docs / "tutorial_en.html"
        if html.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(html)))
            return
        pdf = docs / "tutorial_en.pdf"
        if pdf.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf)))
        edition = T("PRO") if is_pro() else T("Free")
        QMessageBox.about(
            self, T("About FileCopier"),
            T("about_text", name=APP_NAME, version=APP_VERSION, edition=edition,
              price=f"{PRO_PRICE_USD:.0f}", email=CONTACT_EMAIL, logpath=log_path()),
        )

    @safe
    def _check_updates(self):
        from core.updates import latest_release, is_newer_than_local
        from core.version import GITHUB_REPO
        from PySide6.QtCore import QThread as _QThread, Signal as _Signal

        if not GITHUB_REPO:
            QMessageBox.information(
                self, T("Updates"),
                T("Update check is not configured yet.\nOnce published on GitHub, this button will notify you when new versions are released.")
            )
            return

        import urllib.error

        class _Worker(_QThread):
            done = _Signal(dict)

            def run(self):
                try:
                    self.done.emit(latest_release() or {})
                except (urllib.error.URLError, OSError, ValueError):
                    self.done.emit({})

        self._update_worker = _Worker(self)
        self._update_worker.done.connect(self._on_update_result)
        self._update_worker.start()

    def _on_update_result(self, info: dict):
        from core.updates import is_newer_than_local
        if not info:
            QMessageBox.information(
                self, T("Updates"),
                T("Could not check GitHub right now. Check your connection and try again.")
            )
            return
        tag = info.get("tag", "")
        if tag and is_newer_than_local(tag):
            QMessageBox.information(
                self, T("Update available"),
                T("A new version is available: <b>{tag}</b>\n\nDownload it here:\n{url}", tag=tag, url=info.get("url", ""))
            )
        else:
            QMessageBox.information(
                self, T("Updates"),
                T("You have the latest version ({version}).", version=APP_VERSION)
            )

    def _check_free_limit(self, n: int) -> bool:
        """Devuelve True si hay que bloquear la copia (gratis + límite)."""
        if n <= FREE_MAX_FILES or is_pro():
            return False
        QMessageBox.information(
            self, T("Free limit"),
            T("You selected {n} files, but the free version\ncopies up to {limit} files per operation.\n\nThe <b>Pro</b> version copies without limit, plus unlimited filters\nand advanced duplicate renaming.\n\nPro menu → Activate Pro license...", n=n, limit=FREE_MAX_FILES)
        )
        return True

    def _open_log(self):
        try:
            dlg = LogViewer(self)
            dlg.exec()
        except Exception as e:
            log_error(f"_open_log: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def _update_status(self):
        selected = self.tree.get_selected_file_infos()
        n = len(selected)
        total_size = sum(f.size for f in selected)
        dups = sum(1 for lst in find_duplicate_names(selected).values() if len(lst) > 1)
        parts = [
            T("Selected: {n} · Size: {size} · Files: {files} · Folders: {folders}",
              n=n, size=format_size(total_size),
              files=self.tree.get_visible_count(),
              folders=self.tree.get_folder_count()),
        ]
        if dups:
            parts.append(T("Duplicates: {n}", n=dups))
        self.status_label.setText(" · ".join(parts))

    def _check_all(self, state: bool):
        if state:
            progress = QProgressDialog(T("Selecting all files..."), T("Cancel"), 0, 0, self)
            progress.setWindowTitle(T("Select all"))
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.setCancelButton(None)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            self.tree.check_all(True)
            progress.close()
        else:
            self.tree.check_all(False)

    @safe
    def _browse_source(self):
        path = QFileDialog.getExistingDirectory(self, T("Select source folder"))
        if path:
            self.src_input.setText(path)
            log(f"Origen seleccionado: {path}")

    @safe
    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, T("Select destination folder"))
        if path:
            self.dst_input.setText(path)
            log(f"Destino seleccionado: {path}")

    def _parse_filters(self):
        show = self.filter_show.text().strip()
        hide = self.filter_hide.text().strip()
        show_exts = None
        if show:
            ext_list = []
            for e in show.split(","):
                e = e.strip().lower()
                if not e:
                    continue
                if not e.startswith("."):
                    e = "." + e
                ext_list.append(e)
            if ext_list:
                show_exts = ext_list
        hide_keywords = [h.strip().lower() for h in hide.split(",") if h.strip()] if hide else None
        return show_exts, hide_keywords

    @safe
    def _load_tree(self):
        src = self.src_input.text().strip()
        if not src:
            QMessageBox.warning(self, T("Error"), T("Select a source folder."))
            return

        src_path = Path(src)
        if not src_path.is_dir():
            QMessageBox.warning(self, T("Error"), T("Source path does not exist."))
            return

        log(f"Cargando árbol de origen: {src}")
        t0 = time.time()
        self.source_path = src_path
        show_exts, hide_keywords = self._parse_filters()
        self.tree.load_root(src_path, show_exts, hide_keywords)

        count = self.tree.get_visible_count()
        self.btn_copy.setEnabled(True)
        self.btn_multi.setEnabled(True)
        self.btn_summary.setEnabled(True)
        self.btn_adv_filters.setEnabled(True)
        log(T("Tree loaded: {count} files visible in {seconds}s", count=count, seconds=f"{time.time()-t0:.2f}"))

    @safe
    def _apply_filters(self):
        if not self.tree.root_path:
            return
        log("Aplicando filtros de extensión/palabras clave")
        show_exts, hide_keywords = self._parse_filters()
        self.tree._show_exts = show_exts
        self.tree._hide_keywords = hide_keywords
        self.tree.apply_filter_visibility(show_exts, hide_keywords)
        count = self.tree.get_visible_count()
        log(f"Filtros aplicados: {count} visibles")

    @safe
    def _show_summary(self):
        selected = self.tree.get_selected_file_infos()
        log(f"Ver resumen: {len(selected)} archivos seleccionados")
        if not selected:
            QMessageBox.information(self, T("No selection"), T("No files selected."))
            return
        dialog = SummaryDialog(selected, self.source_path, self)
        dialog.exec()

    @safe
    def _open_adv_filters(self):
        log("Abriendo filtros avanzados")
        dlg = FilterDialog(self.tree, self)
        dlg.show()

    def _show_copy_options(self, selected_files) -> bool:
        dlg = CopyOptionsDialog(selected_files, self)
        return dlg.exec() == CopyOptionsDialog.Accepted

    def _dest_inside_source(self, dest: Path) -> bool:
        """True si el destino es el origen o está dentro de él (evita copiar
        la carpeta dentro de sí misma)."""
        if not self.source_path:
            return False
        try:
            src = self.source_path.resolve()
            dst = dest.resolve()
        except OSError:
            return False
        if dst == src:
            return True
        try:
            dst.relative_to(src)
            return True
        except ValueError:
            return False

    def _run_copy_worker(self, files, dest_path: Path, conflict_map: dict, flat: bool,
                         rename_map: Optional[dict] = None):
        import time as _time
        t0 = _time.time()
        self.worker = CopyWorker(files, dest_path, conflict_map, flat=flat, rename_map=rename_map)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        dialog = ProgressDialog(self.worker, self.thread, len(files), self)
        self.thread.start()
        dialog.exec()
        elapsed = _time.time() - t0
        log_copy(len(files), str(dest_path), flat, elapsed,
                 dialog._ok_count if hasattr(dialog, '_ok_count') else 0,
                 dialog._err_count if hasattr(dialog, '_err_count') else 0)

    def _start_copy(self):
        try:
            dest = self.dst_input.text().strip()
            if not dest:
                QMessageBox.warning(self, T("Error"), T("Select a destination folder."))
                return

            log(f"Inicio copia: destino={dest}")
            dest_path = Path(dest)
            if not dest_path.is_dir():
                try:
                    dest_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    QMessageBox.warning(self, T("Error"), T("Could not create {dest}:\n{e}\nSkipping this destination.", dest=dest_path, e=e))
                    return

            self.dest_path = dest_path
            if self._dest_inside_source(dest_path):
                QMessageBox.warning(
                    self, T("Invalid destination"),
                    T("The destination cannot be the source folder or inside it.")
                )
                return
            selected_files = self.tree.get_selected_file_infos()
            if not selected_files:
                QMessageBox.information(self, T("No selection"), T("No files selected."))
                return
            if self._check_free_limit(len(selected_files)):
                return

            # Copy options dialog (structure / flat + duplicates)
            dlg = CopyOptionsDialog(selected_files, self)
            if dlg.exec() != CopyOptionsDialog.Accepted:
                return
            flat = dlg.flat

            if self.tree.has_hidden_selected():
                reply = QMessageBox.question(
                    self, T("Active filter"),
                    T("There are selected files hidden by the filter that will be copied.\nShow the copy summary?"),
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    SummaryDialog(selected_files, self.source_path, self).exec()

            # Duplicate name handling for flat mode
            conflict_map = {}
            rename_map = {}
            if flat:
                if dlg.dup_action == "skip":
                    seen = set()
                    deduped = []
                    for f in selected_files:
                        if f.name not in seen:
                            seen.add(f.name)
                            deduped.append(f)
                    selected_files = deduped
                else:
                    rename_map = build_flat_rename_map(selected_files)

            conflicts = check_conflicts(selected_files, dest_path, flat=flat, rename_map=rename_map)
            if conflicts:
                dialog = ConflictDialog(conflicts, self)
                if dialog.exec() != ConflictDialog.Accepted:
                    return
                decision = dialog.get_decision()
                if decision == "skip":
                    for _, d in conflicts:
                        conflict_map[str(d)] = "skip"
                elif decision == "rename":
                    for _, d in conflicts:
                        conflict_map[str(d)] = "rename"

            reply = QMessageBox.question(
                self, T("Confirm copy"),
                T("Files to copy: {n}\nDestination: {dest}\n\nProceed?", n=len(selected_files), dest=dest_path),
                QMessageBox.Yes | QMessageBox.Cancel
            )
            if reply != QMessageBox.Yes:
                return

            log_info(f"Inicio copia: {len(selected_files)} archivos → {dest_path} flat={flat}")
            self._run_copy_worker(selected_files, dest_path, conflict_map, flat, rename_map)
        except Exception as e:
            import traceback
            log_error(f"_start_copy: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, T("Error"), T("Error copying:\n{e}", e=e))

    def _start_multi_copy(self):
        try:
            selected_files = self.tree.get_selected_file_infos()
            log(f"Inicio multi-copia: {len(selected_files)} archivos seleccionados")
            if not selected_files:
                QMessageBox.information(self, "Sin selección", "No hay archivos seleccionados.")
                return
            if self._check_free_limit(len(selected_files)):
                return

            # Copy options first
            dlg = CopyOptionsDialog(selected_files, self)
            if dlg.exec() != CopyOptionsDialog.Accepted:
                return
            flat = dlg.flat
            skip_dups = flat and dlg.dup_action == "skip"
            rename_map = {}
            if flat and not skip_dups:
                rename_map = build_flat_rename_map(selected_files)

            # Deduplicate if needed
            if skip_dups:
                seen = set()
                deduped = []
                for f in selected_files:
                    if f.name not in seen:
                        seen.add(f.name)
                        deduped.append(f)
                selected_files = deduped

            # Open multi-dest dialog
            dest_root = self.dst_input.text().strip()
            multi = MultiDestDialog(dest_root, self)
            if multi.exec() != MultiDestDialog.Accepted:
                return
            destinations = multi.selected_destinations

            log_info(f"Inicio multi-copia: {len(selected_files)} archivos → {len(destinations)} destinos")

            total_dests = len(destinations)
            for idx, dest_str in enumerate(destinations):
                dest_path = Path(dest_str)
                if self._dest_inside_source(dest_path):
                    QMessageBox.warning(
                        self, T("Invalid destination"),
                        T("destination inside source, skipping", dest=dest_path)
                    )
                    log_error(f"multi-copy: destino dentro del origen omitido: {dest_path}")
                    continue
                if not dest_path.is_dir():
                    try:
                        dest_path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        QMessageBox.warning(
                            self, T("Error"),
                            T("Could not create {dest}:\n{e}\nSkipping this destination.", dest=dest_path, e=e)
                        )
                        log_error(f"multi-copy: no se pudo crear {dest_path}: {e}")
                        continue

                reply = QMessageBox.question(
                    self, T("Confirm copy"),
                    T("Multi-dest confirm", i=idx+1, n=total_dests, dest=dest_path, nfiles=len(selected_files)),
                    QMessageBox.Yes | QMessageBox.Cancel
                )
                if reply != QMessageBox.Yes:
                    continue

                conflict_map = {}
                conflicts = check_conflicts(selected_files, dest_path, flat=flat, rename_map=rename_map)
                if conflicts:
                    cdlg = ConflictDialog(conflicts, self)
                    if cdlg.exec() != ConflictDialog.Accepted:
                        continue
                    decision = cdlg.get_decision()
                    if decision == "skip":
                        for _, d in conflicts:
                            conflict_map[str(d)] = "skip"
                    elif decision == "rename":
                        for _, d in conflicts:
                            conflict_map[str(d)] = "rename"

                self._run_copy_worker(selected_files, dest_path, conflict_map, flat, rename_map)
        except Exception as e:
            import traceback
            log_error(f"_start_multi_copy: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, T("Error"), T("Error in multi-copy:\n{e}", e=e))
