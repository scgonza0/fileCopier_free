import sys
import os
import json
import tempfile
import shutil
import time
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Fijamos el idioma en tests para que las aserciones de texto sean deterministas.
os.environ.setdefault("FC_LANG", "es")
from core.i18n import T  # noqa: E402  (importa después de setear FC_LANG)

from pathlib import Path
from datetime import datetime, timedelta

from core.models import FileInfo
from core.filter_engine import (
    FilterRule, FilterPreset,
    evaluate_rule, match,
    load_preset, save_preset, parse_size,
    CONFIG_FILE,
)
from core.scanner import scan_level, scan_full

# ── Helpers ──
tests_run = 0
tests_passed = 0
tests_failed = []


def check(condition, msg):
    global tests_run, tests_passed
    tests_run += 1
    if condition:
        tests_passed += 1
        print(f"  [OK] {msg}")
    else:
        tests_failed.append(msg)
        print(f"  [FAIL] {msg}")


# ═══════════════════════════════════════════════════════════
# PARTE 1: UNIT TESTS (sin GUI)
# ═══════════════════════════════════════════════════════════

def test_parse_size():
    print("\n--- parse_size ---")
    check(parse_size("500b") == 500, "parse_size('500b') == 500")
    check(parse_size("1024") == 1024, "parse_size('1024') == 1024  (sin sufijo)")
    check(parse_size("0b") == 0, "parse_size('0b') == 0")

    # Bare numbers (no suffix) work because they fall through to int(float())
    check(parse_size("2048") == 2048, "parse_size('2048') == 2048")

    # Suffixes are matched longest-first, so "kb"/"mb"/"gb" work correctly
    check(parse_size("1KB") == 1024, "parse_size('1KB') == 1024")
    check(parse_size("2MB") == 2 * 1024**2, "parse_size('2MB') == 2MB")
    check(parse_size("1GB") == 1024**3, "parse_size('1GB') == 1GB")
    check(parse_size("500mb") == 500 * 1024**2, "parse_size('500mb') == 500MB")


def test_evaluate_rule_all_fields():
    print("\n--- evaluate_rule (todos los campos y operadores) ---")
    now = datetime.now()
    fi = FileInfo(
        path=Path("/fake/docs/Informe2024.pdf"),
        name="Informe2024.pdf",
        size=4096,
        modified=now - timedelta(days=3),
        is_dir=False,
        relative_path="docs/Informe2024.pdf",
        extension=".pdf",
    )

    # -- name --
    r = FilterRule(enabled=True, field="name", operator="contains", value="orme")
    check(evaluate_rule(fi, r), "name contains 'orme'")

    r = FilterRule(enabled=True, field="name", operator="not_contains", value="XYZ")
    check(evaluate_rule(fi, r), "name not_contains 'XYZ'")

    r = FilterRule(enabled=True, field="name", operator="equals", value="informe2024")
    check(evaluate_rule(fi, r), "name equals 'informe2024' (stem, sin extension)")

    r = FilterRule(enabled=True, field="name", operator="starts_with", value="Info")
    check(evaluate_rule(fi, r), "name starts_with 'Info'")

    r = FilterRule(enabled=True, field="name", operator="ends_with", value="2024")
    check(evaluate_rule(fi, r), "name ends_with '2024' (stem 'informe2024')")

    r = FilterRule(enabled=True, field="name", operator="ends_with", value=".pdf")
    check(not evaluate_rule(fi, r), "name ends_with '.pdf' NO matchea (name es el stem, sin extension)")

    r = FilterRule(enabled=True, field="name", operator="regex", value=r"\d{4}$")
    check(evaluate_rule(fi, r), "name regex matchea 4 digitos al final del stem")

    r = FilterRule(enabled=True, field="name", operator="regex", value="[")
    check(not evaluate_rule(fi, r), "name regex '[' (regex invalido) retorna False")

    # -- extension --
    r = FilterRule(enabled=True, field="extension", operator="is", value=".pdf")
    check(evaluate_rule(fi, r), "extension is '.pdf'")

    r = FilterRule(enabled=True, field="extension", operator="is", value="pdf")
    check(evaluate_rule(fi, r), "extension is 'pdf' (sin punto)")

    r = FilterRule(enabled=True, field="extension", operator="is_not", value=".txt")
    check(evaluate_rule(fi, r), "extension is_not '.txt'")

    r = FilterRule(enabled=True, field="extension", operator="is_one_of", value=".pdf,.txt,.csv")
    check(evaluate_rule(fi, r), "extension is_one_of '.pdf,.txt,.csv'")

    r = FilterRule(enabled=True, field="extension", operator="is_one_of", value="pdf")
    check(evaluate_rule(fi, r), "extension is_one_of 'pdf' (sin punto)")

    # -- path --
    r = FilterRule(enabled=True, field="path", operator="contains", value="docs/")
    check(evaluate_rule(fi, r), "path contains 'docs/'")

    r = FilterRule(enabled=True, field="path", operator="not_contains", value="other")
    check(evaluate_rule(fi, r), "path not_contains 'other'")

    # -- size --
    r = FilterRule(enabled=True, field="size", operator="gt", value="1000")
    check(evaluate_rule(fi, r), "size gt '1000' (4096 > 1000)")

    r = FilterRule(enabled=True, field="size", operator="lt", value="5000")
    check(evaluate_rule(fi, r), "size lt '5000' (4096 < 5000)")

    r = FilterRule(enabled=True, field="size", operator="between", value="2000,6000")
    check(evaluate_rule(fi, r), "size between '2000,6000' (4096 en rango)")

    r = FilterRule(enabled=True, field="size", operator="gt", value="5000")
    check(not evaluate_rule(fi, r), "size gt '5000' -> False (4096 no > 5000)")

    # -- size con unidades --
    r = FilterRule(enabled=True, field="size", operator="gt", value="1kb")
    check(evaluate_rule(fi, r), "size gt '1kb' (4096 > 1024)")

    r = FilterRule(enabled=True, field="size", operator="between", value="4kb,2mb")
    check(evaluate_rule(fi, r), "size between '4kb,2mb' (4096 en rango)")

    # -- date --
    r = FilterRule(enabled=True, field="date", operator="last_n_days", value="10")
    check(evaluate_rule(fi, r), "date last_n_days 10 (file is 3d old)")

    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    r = FilterRule(enabled=True, field="date", operator="before", value=tomorrow)
    check(evaluate_rule(fi, r), "date before tomorrow")

    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    r = FilterRule(enabled=True, field="date", operator="after", value=yesterday)
    check(not evaluate_rule(fi, r), "date after yesterday -> False (file is 3d old)")

    ten_ago = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    r = FilterRule(enabled=True, field="date", operator="after", value=ten_ago)
    check(evaluate_rule(fi, r), "date after 10 days ago")

    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    r = FilterRule(enabled=True, field="date", operator="between", value=f"{ten_ago},{yesterday}")
    check(evaluate_rule(fi, r), "date between 10d ago and yesterday (day 3 is in range)")

    # -- date con hora --
    tomorrow_with_time = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    r = FilterRule(enabled=True, field="date", operator="before", value=tomorrow_with_time)
    check(evaluate_rule(fi, r), "date before 'tomorrow HH:MM:SS'")

    three_days_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    r = FilterRule(enabled=True, field="date", operator="before", value=f"{three_days_ago} 23:59")
    check(evaluate_rule(fi, r), "date before '3d ago 23:59' (file es de hace 3d)")

    now_iso_time = now.strftime("%Y-%m-%d %H:%M")
    r = FilterRule(enabled=True, field="date", operator="before", value=now_iso_time)
    check(evaluate_rule(fi, r), "date before 'now HH:MM' (file es de hace 3d)")

    r = FilterRule(enabled=True, field="date", operator="after", value=f"{yesterday} 00:00")
    check(not evaluate_rule(fi, r), "date after 'yesterday 00:00' -> False (file es de hace 3d)")

    # -- hidden --
    fi_hidden = FileInfo(
        path=Path("/fake/.config.ini"), name=".config.ini", size=100,
        modified=now, is_dir=False, relative_path=".config.ini",
    )
    r = FilterRule(enabled=True, field="hidden", operator="is", value="si")
    check(evaluate_rule(fi_hidden, r), "hidden is 'si' -> True para .config.ini")
    check(not evaluate_rule(fi, r), "hidden is 'si' -> False para archivo normal")

    r = FilterRule(enabled=True, field="hidden", operator="is", value="no")
    check(evaluate_rule(fi, r), "hidden is 'no' -> True para archivo normal")

    # -- disabled rule / empty value --
    r = FilterRule(enabled=False, field="name", operator="contains", value="nada")
    check(evaluate_rule(fi, r), "disabled rule retorna True siempre")

    r = FilterRule(enabled=True, field="name", operator="contains", value="")
    check(evaluate_rule(fi, r), "empty value retorna True siempre")


def test_evaluate_rule_name_stem():
    print("\n--- evaluate_rule name: stem matching ---")
    fi = FileInfo(
        path=Path("/fake/documento.pdf"), name="documento.pdf", size=100,
        modified=datetime.now(), is_dir=False, relative_path="documento.pdf",
    )
    r = FilterRule(enabled=True, field="name", operator="contains", value="documento")
    check(evaluate_rule(fi, r), "name contains 'documento' matchea 'documento.pdf' (stem)")

    r = FilterRule(enabled=True, field="name", operator="starts_with", value="documento")
    check(evaluate_rule(fi, r), "name starts_with 'documento' matchea 'documento.pdf' (stem)")

    fi2 = FileInfo(
        path=Path("/fake/mi_archivo.txt"), name="mi_archivo.txt", size=100,
        modified=datetime.now(), is_dir=False, relative_path="mi_archivo.txt",
        extension=".txt",
    )
    r = FilterRule(enabled=True, field="name", operator="equals", value="mi_archivo")
    check(evaluate_rule(fi2, r), "name equals 'mi_archivo' matchea 'mi_archivo.txt' (stem)")


def test_evaluate_rule_name_equals_dot_pdf():
    print("\n--- evaluate_rule name: equals '.pdf' ---")
    fi_pdf = FileInfo(
        path=Path("/fake/documento.pdf"), name="documento.pdf", size=100,
        modified=datetime.now(), is_dir=False, relative_path="documento.pdf",
        extension=".pdf",
    )
    r = FilterRule(enabled=True, field="name", operator="equals", value=".pdf")
    check(not evaluate_rule(fi_pdf, r), "name equals '.pdf' NO matchea 'documento.pdf'")

    fi_dot = FileInfo(
        path=Path("/fake/.pdf"), name=".pdf", size=100,
        modified=datetime.now(), is_dir=False, relative_path=".pdf",
    )
    check(evaluate_rule(fi_dot, r), "name equals '.pdf' SI matchea '.pdf'")

    # extension field is the correct way to match extensions
    r_ext = FilterRule(enabled=True, field="extension", operator="is", value=".pdf")
    check(evaluate_rule(fi_pdf, r_ext), "extension is '.pdf' SI matchea 'documento.pdf'")


def test_match():
    print("\n--- match() ---")
    files = [
        FileInfo(Path(f"{i}.txt"), f"{i}.txt", 100, datetime.now(), False, f"{i}.txt")
        for i in range(3)
    ]
    r1 = FilterRule(enabled=True, field="name", operator="contains", value="1")
    r2 = FilterRule(enabled=True, field="name", operator="contains", value="2")

    # -- AND --
    preset = FilterPreset(enabled=True, logic="AND", rules=[r1, r2])
    result = match(preset, files)
    check(len(result) == 0, "AND con reglas excluyentes -> 0 archivos")

    # -- OR --
    preset.logic = "OR"
    result = match(preset, files)
    check(len(result) == 2, "OR -> 2 archivos (1.txt y 2.txt)")

    # -- regla desactivada --
    r2.enabled = False
    result = match(preset, files)
    check(len(result) == 1, "r2 desactivada -> solo 1 archivo")

    # -- sin reglas activas -> todos pasan --
    r1.enabled = False
    r2.enabled = False
    result = match(preset, files)
    check(len(result) == 3, "ninguna regla activa -> todos pasan (3)")

    # -- lista de reglas vacia -> todos pasan --
    preset.rules = []
    result = match(preset, files)
    check(len(result) == 3, "reglas vacias -> todos pasan (3)")

    # -- preset desactivado --
    preset.enabled = False
    result = match(preset, files)
    check(len(result) == 3, "preset desactivado -> todos pasan (3)")


def test_preset_persistence():
    print("\n--- load_preset / save_preset ---")
    import core.filter_engine as fe
    orig_cfg = fe.CONFIG_FILE
    try:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fe.CONFIG_FILE = td_path / "test_filters.json"

            preset = FilterPreset(
                enabled=True,
                logic="AND",
                rules=[
                    FilterRule(enabled=True, scan_all=True, field="name", operator="contains", value="test"),
                    FilterRule(enabled=False, scan_all=False, field="extension", operator="is", value=".pdf"),
                ],
            )
            save_preset(preset)

            loaded = load_preset()
            check(loaded.enabled is True, "enabled=True se persiste")
            check(loaded.logic == "AND", "logic=AND se persiste")
            check(len(loaded.rules) == 2, "2 reglas guardadas/cargadas")

            r0 = loaded.rules[0]
            check(r0.enabled is True, "rule[0] enabled=True")
            check(r0.scan_all is True, "rule[0] scan_all=True")
            check(r0.field == "name", "rule[0] field=name")
            check(r0.operator == "contains", "rule[0] operator=contains")
            check(r0.value == "test", "rule[0] value=test")

            r1 = loaded.rules[1]
            check(r1.enabled is False, "rule[1] enabled=False se persiste")
            check(r1.field == "extension", "rule[1] field=extension")

            # -- enabled=False en preset --
            preset.enabled = False
            save_preset(preset)
            loaded = load_preset()
            check(loaded.enabled is False, "enabled=False se persiste en preset")

            # -- sin archivo --
            fe.CONFIG_FILE = td_path / "nonexistent.json"
            fallback = load_preset()
            check(fallback.enabled is True, "carga fallida devuelve FilterPreset() con enabled=True")
            check(len(fallback.rules) == 0, "carga fallida devuelve 0 reglas")
    finally:
        fe.CONFIG_FILE = orig_cfg


def test_scan_level():
    print("\n--- scan_level ---")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "beta.txt").write_text("b")
        (root / "alpha.txt").write_text("a")
        sub = root / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")

        entries = scan_level(root, root)
        check(len(entries) == 3, f"3 entradas en raiz, got {len(entries)}")
        check(entries[0].is_dir, "primera entrada es directorio")
        check(entries[0].name == "subdir", f"primera = 'subdir', got '{entries[0].name}'")
        check(entries[1].name == "alpha.txt", "segunda = 'alpha.txt' (orden alfabetico)")
        check(entries[2].name == "beta.txt", "tercera = 'beta.txt'")

        # -- show_exts --
        entries = scan_level(root, root, show_exts=[".txt"])
        check(len(entries) == 3, "show_exts .txt -> 3 (dir + 2 .txt)")

        entries = scan_level(root, root, show_exts=[".py"])
        check(len(entries) == 1, "show_exts .py -> solo directorio (sin .py)")
        check(entries[0].is_dir, "unica entrada es el directorio")

        # -- hide_keywords --
        entries = scan_level(root, root, hide_keywords=["alpha"])
        check(len(entries) == 2, "hide 'alpha' -> 2 (subdir + beta.txt)")
        names = [e.name for e in entries]
        check("subdir" in names, "subdir presente")
        check("beta.txt" in names, "beta.txt presente")
        check("alpha.txt" not in names, "alpha.txt oculto")

        # -- dir dentro de dir no aparece en scan_level de raiz --
        check(all(e.name != "nested.txt" for e in entries), "nested.txt no aparece (esta en subdir)")


def test_scan_full():
    print("\n--- scan_full ---")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "top.txt").write_text("top")
        sub = root / "sub"
        sub.mkdir()
        (sub / "mid.txt").write_text("mid")
        deep = sub / "deep"
        deep.mkdir()
        (deep / "bottom.txt").write_text("bottom")

        entries = scan_full(root)
        check(len(entries) == 5, f"5 entradas (3 files + 2 dirs), got {len(entries)}")

        names = [e.name for e in entries]
        check("top.txt" in names, "top.txt encontrado")
        check("mid.txt" in names, "mid.txt encontrado")
        check("bottom.txt" in names, "bottom.txt encontrado")
        check("sub" in names, "dir 'sub' encontrado")
        check("deep" in names, "dir 'deep' encontrado")

        files_only = [e for e in entries if not e.is_dir]
        check(len(files_only) == 3, "3 archivos (no directorios)")
        check(all(e.size > 0 for e in files_only), "todos los archivos tienen size > 0")
        check(all(e.relative_path for e in files_only), "todos tienen relative_path no vacio")

        # -- progress callback (solo se llama cada 50 items, arbol chico puede no dispararlo) --
        progress_calls = []

        def cb(cur, total):
            progress_calls.append((cur, total))

        scan_full(root, cb)
        check(len(progress_calls) > 0, "progress callback fue llamado (cache hit)")
        if progress_calls:
            cur, total = progress_calls[-1]
            check(isinstance(cur, int) and isinstance(total, int), "callback recibe enteros")
            check(total == len(entries), f"total del callback coincide ({total})")


# ═══════════════════════════════════════════════════════════
# PARTE 2: GUI TESTS (con QApplication)
# ═══════════════════════════════════════════════════════════

def _get_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_file_tree_widget():
    print("\n--- GUI: FileTreeWidget ---")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from ui.tree_widget import FileTreeWidget

    _get_app()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "gamma.txt").write_text("g")
        (root / "alpha.txt").write_text("a")
        sub = root / "carpeta"
        sub.mkdir()
        (sub / "delta.txt").write_text("d")
        (sub / "beta.txt").write_text("b")

        widget = FileTreeWidget()
        widget.load_root(root)
        QApplication.processEvents()

        # -- carga primer nivel --
        check(widget.topLevelItemCount() == 3, f"3 items top-level, got {widget.topLevelItemCount()}")

        item0 = widget.topLevelItem(0)
        check(item0 is not None, "item 0 existe")
        check(item0.text(0) == "carpeta", f"primer item = 'carpeta', got '{item0.text(0)}'")
        check(item0.checkState(0) == Qt.Unchecked, "directorio inicia sin check")

        item1 = widget.topLevelItem(1)
        check(item1.text(0) == "alpha.txt", f"segundo = 'alpha.txt', got '{item1.text(0)}'")
        check(item1.checkState(0) == Qt.Unchecked, "archivo inicia sin check")
        check(item1.text(1) == "1 B", "archivo muestra tamano en columna 1")

        # -- checkar un item --
        item1.setCheckState(0, Qt.Checked)
        QApplication.processEvents()
        check(item1.checkState(0) == Qt.Checked, "setCheckState funciona")

        selected = widget.get_selected_file_infos()
        check(len(selected) == 1, "get_selected_file_infos retorna 1 archivo")
        check(selected[0].name == "alpha.txt", "archivo seleccionado es alpha.txt")

        # -- expandir directorio (lazy loading) --
        item0.setExpanded(True)
        QApplication.processEvents()
        check(item0.childCount() > 0, f"directorio expandido tiene hijos, got {item0.childCount()}")
        if item0.childCount() >= 2:
            child_names = [item0.child(i).text(0) for i in range(item0.childCount())]
            check("beta.txt" in child_names, "beta.txt aparece en subdirectorio")
            check("delta.txt" in child_names, "delta.txt aparece en subdirectorio")

        # -- check_all --
        widget.check_all(True)
        QApplication.processEvents()
        all_sel = widget.get_selected_file_infos()
        # gamma.txt, alpha.txt + beta.txt, delta.txt (inside carpeta/) = 4 files
        check(len(all_sel) == 4, f"check_all -> 4 archivos (3 raiz + 1 en carpeta/), got {len(all_sel)}")

        widget.check_all(False)
        QApplication.processEvents()
        all_sel = widget.get_selected_file_infos()
        check(len(all_sel) == 0, "check_all(False) -> 0 archivos seleccionados")

        widget.deleteLater()


def test_filter_dialog():
    print("\n--- GUI: FilterDialog ---")
    import core.filter_engine as fe
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtTest import QTest
    from ui.tree_widget import FileTreeWidget
    from ui.filter_dialog import FilterDialog

    _get_app()

    # Aislar config: que no cargue presets guardados en %APPDATA (que podrían
    # tener >=2 reglas y disparar el modal de free-limit → cuelgue en offscreen).
    orig_cfg = fe.CONFIG_FILE
    with tempfile.TemporaryDirectory() as td_cfg:
        fe.CONFIG_FILE = Path(td_cfg) / "test_filter_dialog.json"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data.txt").write_text("data")
            (root / "info.csv").write_text("info")

            tree = FileTreeWidget()
            tree.load_root(root)
            QApplication.processEvents()

            dialog = FilterDialog(tree)
            QApplication.processEvents()

            initial_rows = len(dialog._rows)
            check(dialog.cb_master is not None, "master checkbox existe")
            # El config existente no tiene "enabled", por lo que load_preset() lo
            # inicializa en True; verificamos que existe y se puede toggle
            dialog.cb_master.setChecked(False)
            check(dialog.cb_master.isChecked() is False, "master se puede desactivar")

            # -- agregar regla --
            dialog._add_row()
            QApplication.processEvents()
            check(len(dialog._rows) == initial_rows + 1, f"se agrego 1 regla ({initial_rows} -> {len(dialog._rows)})")

            new_row = dialog._rows[-1]
            check(new_row.cb_enabled.isChecked() is False, "nueva regla inicia desactivada")

            # -- activar presete --
            dialog.cb_master.setChecked(True)
            QApplication.processEvents()
            check(dialog.cb_master.isChecked(), "master toggle funciona")

            # -- editar regla --
            new_row.value_input.setText("data")
            QApplication.processEvents()
            check(new_row.value_input.text() == "data", "se puede editar el valor de la regla")

            rule_obj = new_row.to_rule()
            check(rule_obj.field == "name", "regla por defecto es field=name")
            check(rule_obj.value == "data", "to_rule() refleja el valor editado")

            # -- eliminar regla --
            dialog._remove_row(new_row)
            QApplication.processEvents()
            check(len(dialog._rows) == initial_rows, f"se elimino la regla ({len(dialog._rows)} == {initial_rows})")

            dialog.close()
            tree.deleteLater()
    fe.CONFIG_FILE = orig_cfg


def test_preview_dialog():
    print("\n--- GUI: PreviewDialog ---")
    from PySide6.QtWidgets import QApplication
    from ui.preview_dialog import PreviewDialog
    from ui.tree_widget import FileTreeWidget

    _get_app()

    now = datetime.now()
    mock_files = [
        FileInfo(Path("/fake/a.txt"), "a.txt", 512, now, False, "a.txt"),
        FileInfo(Path("/fake/sub/b.txt"), "b.txt", 2048, now, False, "sub/b.txt"),
    ]

    tree = FileTreeWidget()
    dialog = PreviewDialog(mock_files, tree)
    QApplication.processEvents()

    check(dialog.tree.topLevelItemCount() > 0, f"preview tree tiene items, got {dialog.tree.topLevelItemCount()}")

    # buscar archivos en el arbol
    all_items = []
    for i in range(dialog.tree.topLevelItemCount()):
        all_items.append(dialog.tree.topLevelItem(i))
        for j in range(dialog.tree.topLevelItem(i).childCount()):
            all_items.append(dialog.tree.topLevelItem(i).child(j))

    texts = [it.text(0) for it in all_items]
    check("a.txt" in texts, "preview muestra 'a.txt'")
    check("b.txt" in texts, "preview muestra 'b.txt'")
    check("sub" in texts, "preview muestra directorio 'sub'")

    file_items = [it for it in all_items if it.text(0) in ("a.txt", "b.txt")]
    for fi in file_items:
        check(fi.text(1) != "", f"'{fi.text(0)}' tiene tamano en columna 1")

    dialog.close()
    tree.deleteLater()


# ── Tests de huella de PC (machine_id) ─────────────────────────
def test_machine_id_deterministic():
    from core.machine import machine_id
    a = machine_id()
    b = machine_id()
    check(a == b, f"machine_id deterministic: {a} == {b}")
    check(len(a) == 16, f"machine_id len 16, got {len(a)}")
    import re
    check(bool(re.fullmatch(r"[0-9a-f]{16}", a)), f"machine_id is 16-hex, got '{a}'")


def test_machine_id_legacy_compat():
    from core.machine import machine_id, machine_id_legacy
    current = machine_id()
    legacy = machine_id_legacy()
    # Legacy debe ser un hash válido distinto (sin sensor SMBIOS)
    check(len(legacy) == 16, f"machine_id_legacy len 16, got {len(legacy)}")
    import re
    check(bool(re.fullmatch(r"[0-9a-f]{16}", legacy)), f"legacy is 16-hex, got '{legacy}'")
    # _machine_match acepta ambos formatos
    from core.config import _machine_match
    check(_machine_match({"machine": current}) is True, "machine_match acepta formato actual")
    check(_machine_match({"machine": legacy}) is True, "machine_match acepta formato legacy")
    check(_machine_match({"machine": "0" * 16}) is False, "machine_match rechaza huella ajena")
    check(_machine_match({}) is True, "machine_match acepta clave sin binding")


def test_smbios_sensor_present():
    from core.machine import _sensors
    sensors = _sensors()
    # Debe haber al menos un sensor (siempre hay fallback P:)
    check(len(sensors) >= 1, f"_sensors devuelve al menos 1, got {len(sensors)}")
    # El último sensor es siempre el fallback de plataforma
    check(sensors[-1].startswith("P:"), f"último sensor es fallback P:, got '{sensors[-1]}'")


def test_cross_platform_sensor_branching():
    """_sensors() debe ramificar por plataforma (Windows/macOS/Linux)."""
    import core.machine as m
    sensors = m._sensors()
    if m._IS_WINDOWS:
        # Windows tiene sensores S: G: V: M: P: (algunos pueden fallar en CI)
        check(any(s.startswith("P:") for s in sensors),
              f"Windows: sensor P: presente, got {sensors}")
    elif m._IS_MACOS:
        check(any(s.startswith("U:") for s in sensors) or any(s.startswith("P:") for s in sensors),
              f"macOS: sensor U: o P: presente, got {sensors}")
        check(sensors[-1].startswith("P:"), f"macOS: último sensor P:, got {sensors[-1]}")
    elif m._IS_LINUX:
        check(any(s.startswith("U:") for s in sensors) or any(s.startswith("P:") for s in sensors),
              f"Linux: sensor U: o P: presente, got {sensors}")
        check(sensors[-1].startswith("P:"), f"Linux: último sensor P:, got {sensors[-1]}")
    # En todos los casos, machine_id debe ser válido
    mid = m.machine_id()
    check(len(mid) == 16, f"machine_id len 16 en esta plataforma, got {len(mid)}")


def test_machine_id_cross_platform_stable():
    """machine_id debe ser estable en la misma máquina (cualquier plataforma)."""
    from core.machine import machine_id
    a = machine_id()
    b = machine_id()
    check(a == b, f"machine_id estable: {a} == {b}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    start = time.time()

    unit_tests = [
        ("parse_size", test_parse_size),
        ("evaluate_rule (todos los campos)", test_evaluate_rule_all_fields),
        ("evaluate_rule (stem matching)", test_evaluate_rule_name_stem),
        ("evaluate_rule (equals .pdf)", test_evaluate_rule_name_equals_dot_pdf),
        ("match()", test_match),
        ("persistencia preset", test_preset_persistence),
        ("scan_level", test_scan_level),
        ("scan_full", test_scan_full),
        ("machine_id_deterministic", test_machine_id_deterministic),
        ("machine_id_legacy_compat", test_machine_id_legacy_compat),
        ("smbios_sensor_present", test_smbios_sensor_present),
        ("cross_platform_sensor_branching", test_cross_platform_sensor_branching),
        ("machine_id_cross_platform_stable", test_machine_id_cross_platform_stable),
    ]

    gui_tests = [
        ("FileTreeWidget", test_file_tree_widget),
        ("FilterDialog", test_filter_dialog),
        ("PreviewDialog", test_preview_dialog),
    ]

    print("=" * 60)
    print("  FILECOPIER — TEST SUITE")
    print("=" * 60)

    print("\n>>> PARTE 1: Unit Tests (sin GUI)")
    for name, fn in unit_tests:
        try:
            fn()
        except Exception as e:
            tests_failed.append(f"{name} CRASHED: {e}")
            print(f"  [FAIL] {name} — EXCEPCION:")
            traceback.print_exc()
            print()

    print("\n>>> PARTE 2: GUI Tests (con QApplication)")
    for name, fn in gui_tests:
        try:
            fn()
        except Exception as e:
            tests_failed.append(f"{name} CRASHED: {e}")
            print(f"  [FAIL] {name} — EXCEPCION:")
            traceback.print_exc()
            print()

    elapsed = time.time() - start

    print()
    print("=" * 60)
    print(f"  RESULTADOS")
    print("=" * 60)
    print(f"  Pasados: {tests_passed} / {tests_run}")
    print(f"  Fallados: {tests_run - tests_passed} / {tests_run}")
    print(f"  Tiempo total: {elapsed:.2f}s")

    if tests_failed:
        print(f"\n  Tests fallados ({len(tests_failed)}):")
        for i, msg in enumerate(tests_failed, 1):
            print(f"    {i}. {msg}")

    print()
    if tests_passed == tests_run:
        print("  TODOS LOS TESTS PASARON")
    else:
        print(f"  {(tests_run - tests_passed)} FALLO(S) DETECTADOS")
