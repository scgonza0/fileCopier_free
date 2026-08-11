#!/usr/bin/env bash
# FileCopier — uninstall script (macOS / Linux)
# Uso: ./uninstall.sh
set -euo pipefail

APP_NAME="FileCopier"
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OS="linux"
[[ "$(uname -s)" == "Darwin" ]] && OS="macos"

echo "=== Desinstalando ${APP_NAME} (${OS}) ==="

# Borrar acceso directo
if [[ "$OS" == "macos" ]]; then
    rm -f "${HOME}/Applications/${APP_NAME}.app" 2>/dev/null || true
    echo "  Acceso directo eliminado"
else
    XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
    rm -f "${XDG_DATA_HOME}/applications/${APP_NAME}.desktop" 2>/dev/null || true
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "${XDG_DATA_HOME}/applications" 2>/dev/null || true
    echo "  .desktop eliminado"
fi

# Borrar archivos del programa
rm -rf "${INSTALL_DIR}"
echo "=== Desinstalación completada ==="
