# FileCopier — Copia Selectiva (edición gratuita)

Copiador de archivos para Windows con **copia plana inteligente** y **filtros avanzados**.
Hecho en Python + PySide6. Edición **gratuita y open source** (MIT).

La edición completa, Pro (filtros ilimitados, sin límite de archivos, copia a múltiples
destinos y presets guardados), es propietaria y se activa con licencia aparte — consultar el
repositorio privado del desarrollador.

---

## Funcionalidades

- Explorador de árbol con selección por checkboxes y carga peregosa de carpetas grandes.
- Copiar conservando la estructura de carpetas o **copia plana** (muchos orígenes → una sola carpeta).
- Renombrado de duplicados en copia plana agregando las carpetas que los diferencian
  (ej.: `figura_NEW_FOLDER_(2)_HEC032_NAVIGATION1.fig`).
- Filtros por nombre, extensión y ruta (hasta 2 filtros por operación en esta edición).
- Manejo de conflictos: sobrescribir / omitir / renombrar.
- Log en `%APPDATA%\FileCopier\fileCopier_log.txt`.
- Verificación de actualizaciones (libremente configurable).

---

## Requisitos

- **Windows** (la app y el enlace de máquina Pro son Windows-only).
- Python 3.10+ — *solo necesario para ejecutar desde el código fuente.*
- Las releases instalables son `.exe` autónomos (no requieren Python).

---

## Ejecutar desde el código

```powershell
python -m pip install -r requirements.txt      # PySide6
python main.py
```

Forzar el idioma de la UI:

```powershell
$env:FC_LANG="en" ; python main.py     # o "es"
```

---

## Tutorial de uso

- `docs/tutorial_es.html` (online) / `docs/tutorial_es.pdf` (imprimible)
- `docs/tutorial_en.html` / `docs/tutorial_en.pdf`
- Desde la app: **Ayuda → Ver tutorial de uso**.

---

## Estructura

```
core/   lógica (scanner, copier, filtros, config, actualizaciones, i18n, version)
ui/     ventana principal y diálogos
tests/  suite de tests (pytest: unit + GUI con offscreen)
docs/   tutorial de uso (HTML + PDF, en/es)
```

---

## Licencia

MIT. Esta es la edición gratuita; la versión Pro (filtros ilimitados, sin límites de
archivos, presets, copia múltiple) es de código cerrado y se activa con licencia aparte.
