# FileCopier — install script (Windows PowerShell)
# Uso: .\install.ps1 [-InstallDir "C:\ruta"] [-AcceptEula]
# Nota: es una alternativa al instalador C# (.exe). El instalador oficial
# sigue siendo FileCopier_Setup.exe (FileCopier.exe).
param(
    [string]$InstallDir = "",
    [switch]$AcceptEula
)

$APP_NAME = "FileCopier"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcDir = Split-Path -Parent $ScriptDir

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$APP_NAME"
}

Write-Host "=== Instalando $APP_NAME (Windows) ==="
Write-Host "  Origen:  $SrcDir"
Write-Host "  Destino: $InstallDir"

# 1) Copiar archivos (dist onedir de PyInstaller)
$DistSrc = Join-Path $SrcDir "dist\$APP_NAME"
if (-not (Test-Path $DistSrc)) {
    Write-Error "No se encontro $DistSrc. Compilá primero con PyInstaller."
    exit 1
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path "$DistSrc\*" -Destination $InstallDir -Recurse -Force

# 2) Acceso directo en escritorio y menu inicio
$Shell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('DesktopDirectory')
$StartMenu = [Environment]::GetFolderPath('StartMenu')
$ExePath = Join-Path $InstallDir "$APP_NAME.exe"

# Escritorio
$Shortcut = $Shell.CreateShortcut("$Desktop\$APP_NAME.lnk")
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()
Write-Host "  Acceso directo: $Desktop\$APP_NAME.lnk"

# Menu inicio
$StartMenuDir = Join-Path $StartMenu "Programs\$APP_NAME"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$Shortcut2 = $Shell.CreateShortcut("$StartMenuDir\$APP_NAME.lnk")
$Shortcut2.TargetPath = $ExePath
$Shortcut2.WorkingDirectory = $InstallDir
$Shortcut2.Save()
Write-Host "  Menu inicio: $StartMenuDir\$APP_NAME.lnk"

# 3) Registrar desinstalador
$UninstallScript = Join-Path $InstallDir "uninstall.ps1"
Copy-Item -Path (Join-Path $ScriptDir "uninstall.ps1") -Destination $UninstallScript -Force

Write-Host ""
Write-Host "=== Instalacion completada ==="
Write-Host "  Ejecutar: $ExePath"
Write-Host "  Desinstalar: $UninstallScript"
