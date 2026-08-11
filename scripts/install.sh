#!/usr/bin/env bash
# FileCopier — install script (macOS / Linux)
# Uso: ./install.sh [--dir /ruta/instalacion] [--accept-eula]
set -euo pipefail

APP_NAME="FileCopier"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"

# Detectar plataforma
OS="linux"
if [[ "$(uname -s)" == "Darwin" ]]; then
    OS="macos"
fi

# Directorio de instalación por plataforma
if [[ "$OS" == "macos" ]]; then
    INSTALL_DIR="${HOME}/Applications/${APP_NAME}"
else
    # Linux: XDG compliant
    XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
    INSTALL_DIR="${XDG_DATA_HOME}/${APP_NAME}"
fi

ACCEPT_EULA=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2;;
        --accept-eula) ACCEPT_EULA=1; shift;;
        *) echo "Uso: $0 [--dir /ruta] [--accept-eula]"; exit 1;;
    esac
done

echo "=== Instalando ${APP_NAME} (${OS}) ==="
echo "  Origen:  ${SRC_DIR}"
echo "  Destino: ${INSTALL_DIR}"

# 1) Copiar archivos
mkdir -p "${INSTALL_DIR}"
if [[ "$OS" == "macos" ]]; then
    # En macOS copiamos el .app bundle si existe, o el ejecutable
    if [[ -d "${SRC_DIR}/dist/${APP_NAME}.app" ]]; then
        rm -rf "${INSTALL_DIR}/${APP_NAME}.app"
        cp -R "${SRC_DIR}/dist/${APP_NAME}.app" "${INSTALL_DIR}/"
        EXE_PATH="${INSTALL_DIR}/${APP_NAME}.app/Contents/MacOS/${APP_NAME}"
    else
        cp -R "${SRC_DIR}/dist/${APP_NAME}/"*. "${INSTALL_DIR}/"
        EXE_PATH="$(find "${INSTALL_DIR}" -maxdepth 1 -type f -name '${APP_NAME}*' | head -1)"
    fi
else
    # Linux: copiar directorio onedir de PyInstaller
    if [[ -d "${SRC_DIR}/dist/${APP_NAME}" ]]; then
        cp -R "${SRC_DIR}/dist/${APP_NAME}/"* "${INSTALL_DIR}/"
        EXE_PATH="${INSTALL_DIR}/${APP_NAME}"
    else
        cp -R "${SRC_DIR}/dist/"* "${INSTALL_DIR}/"
        EXE_PATH="$(find "${INSTALL_DIR}" -maxdepth 1 -type f -name '${APP_NAME}*' | head -1)"
    fi
fi

# 2) Acceso directo / integración
if [[ "$OS" == "macos" ]]; then
    # Symlink en ~/Applications
    mkdir -p "${HOME}/Applications"
    ln -sf "${INSTALL_DIR}/${APP_NAME}.app" "${HOME}/Applications/${APP_NAME}.app" 2>/dev/null || true
    echo "  Acceso directo: ~/Applications/${APP_NAME}.app"
else
    # Linux: archivo .desktop
    XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
    APPS_DIR="${XDG_DATA_HOME}/applications"
    mkdir -p "${APPS_DIR}"
    DESKTOP_FILE="${APPS_DIR}/${APP_NAME}.desktop"
    ICON_PATH="${INSTALL_DIR}/../assets/filecopier_256.png"
    if [[ -f "${SRC_DIR}/assets/filecopier_256.png" ]]; then
        ICON_PATH="${SRC_DIR}/assets/filecopier_256.png"
    fi
    cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Selective file copier with advanced filters
Exec=${EXE_PATH}
Icon=${ICON_PATH}
Terminal=false
Categories=Utility;FileTools;
StartupNotify=true
EOF
    chmod +x "${DESKTOP_FILE}"
    # Actualizar cache de escritorio (si está disponible)
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "${APPS_DIR}" 2>/dev/null || true
    echo "  .desktop: ${DESKTOP_FILE}"
fi

# 3) Registrar desinstalador
echo "${INSTALL_DIR}" > "${INSTALL_DIR}/.install_dir"
cat > "${INSTALL_DIR}/uninstall.sh" <<EOF2
#!/usr/bin/env bash
# FileCopier — desinstalador
set -euo pipefail
APP_NAME="${APP_NAME}"
INSTALL_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
OS="${OS}"
echo "=== Desinstalando \${APP_NAME} ==="
# Borrar acceso directo
if [[ "\$OS" == "macos" ]]; then
    rm -f "\${HOME}/Applications/\${APP_NAME}.app" 2>/dev/null || true
else
    XDG_DATA_HOME="\${XDG_DATA_HOME:-\${HOME}/.local/share}"
    rm -f "\${XDG_DATA_HOME}/applications/\${APP_NAME}.desktop" 2>/dev/null || true
fi
# Borrar archivos
rm -rf "\${INSTALL_DIR}"
echo "Desinstalación completada."
EOF2
chmod +x "${INSTALL_DIR}/uninstall.sh"

echo ""
echo "=== Instalación completada ==="
echo "  Ejecutar: ${EXE_PATH}"
echo "  Desinstalar: ${INSTALL_DIR}/uninstall.sh"
