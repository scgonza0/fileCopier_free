# FileCopier — Smart Selective Copy (Free edition)

A Windows file copier built with **Python + PySide6**. This is the **free / open-source
edition** (MIT licensed). The full feature set and Pro upgrade live in the private
developer repository — see [`scgonza0/fileCopier_free`](https://github.com/scgonza0/fileCopier_free)
on GitHub for releases and updates.

---

## Features

- Tree explorer with per-item checkboxes and lazy loading of large folders.
- Copy preserving folder structure, or **flat copy** (many sources → one folder).
- Smart duplicate renaming in flat mode: only the differing parent folders are appended
  (e.g. `figura_NEW_FOLDER_(2)_HEC032_NAVIGATION1.fig`).
- Filters by name, extension and path (up to 2 filters per operation in this edition).
- Conflict handling: overwrite / skip / auto-rename.
- Log at `%APPDATA%\FileCopier\fileCopier_log.txt`.
- Update check configurable via GitHub Releases.

---

## Requirements

- **Windows** (the application and Pro machine binding are Windows-only).
- Python 3.10+ — *only required to run from source.*
- Shipped releases are standalone, self-contained `.exe` (no Python needed to run).

---

## Run from source

```powershell
python -m pip install -r requirements.txt      # PySide6
python main.py
```

Override the UI language:

```powershell
$env:FC_LANG="en" ; python main.py     # or "es"
```

---

## Usage tutorial

- `docs/tutorial_en.html` (online) / `docs/tutorial_en.pdf` (printable)
- `docs/tutorial_es.html` / `docs/tutorial_es.pdf`
- From the app: **Help → View usage tutorial**.

---

## Structure

```
core/   app logic (scanner, copier, filters, config, updates, i18n, version)
ui/     main window and dialogs
tests/  pytest suite (unit + offscreen GUI)
docs/   usage tutorial (HTML + PDF, en/es)
```

---

## License

MIT. This is the free edition; the Pro version (unlimited filters, no file limits,
multi-destination copy, saved presets) is proprietary and activated separately.
