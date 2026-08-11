# FileCopier — uninstall script (Windows PowerShell)
# Uso: .\uninstall.ps1
param()

$APP_NAME = "FileCopier"
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Desinstalando $APP_NAME (Windows) ==="

# Borrar acceso directos
$Desktop = [Environment]::GetFolderPath('DesktopDirectory')
$StartMenu = [Environment]::GetFolderPath('StartMenu')
$StartMenuDir = Join-Path $StartMenu "Programs\$APP_NAME"

Remove-Item -Path "$Desktop\$APP_NAME.lnk" -ErrorAction SilentlyContinue
Remove-Item -Path $StartMenuDir -Recurse -ErrorAction SilentlyContinue
Write-Host "  Accesos directos eliminados"

# Borrar archivos (excepto este script que esta en uso)
Get-ChildItem -Path $InstallDir -File | Where-Object {
    $_.Name -ne "uninstall.ps1"
} | Remove-Item -Force -ErrorAction SilentlyContinue

# Borrar la carpeta (vacio el dir primero)
$ThisScript = Join-Path $InstallDir "uninstall.ps1"
if (Test-Path $ThisScript) { Remove-Item $ThisScript -Force -ErrorAction SilentlyContinue }
Remove-Item -Path $InstallDir -Recurse -ErrorAction SilentlyContinue

Write-Host "=== Desinstalacion completada ==="
