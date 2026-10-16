# Build a Windows release with Nuitka and Inno Setup:
# powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

param(
    [string]$ServerUrl = $env:WOODESK_SERVER_URL
)

$ErrorActionPreference = "Stop"

Write-Host "==> Installing Python dependencies, Nuitka and build tools..."
python -m pip install -r requirements.txt nuitka zstandard ordered-set

if ($ServerUrl) {
    Write-Host "==> Baking in server URL: $ServerUrl"
    (Get-Content app\core\config.py) -replace 'DEFAULT_SERVER_URL = .*', "DEFAULT_SERVER_URL = `"$ServerUrl`"" | Set-Content app\core\config.py
}

# Clean existing build outputs
if (Test-Path dist\WooDesk) {
    Remove-Item -Recurse -Force dist\WooDesk
}
if (Test-Path dist\WooDesk.dist) {
    Remove-Item -Recurse -Force dist\WooDesk.dist
}

Write-Host "==> Compiling native Windows binary using Nuitka (C++ MSVC)..."
python -m nuitka `
  --standalone `
  --enable-plugin=pyside6 `
  --windows-console-mode=disable `
  --assume-yes-for-downloads `
  --include-package=keyring `
  --include-package=markdown `
  --include-data-dir=app/assets=app/assets `
  --output-dir=dist `
  --output-folder-name=WooDesk `
  --output-filename=WooDesk.exe `
  --nofollow-import-to=pytest,unittest `
  run.py

# Nuitka in standalone mode creates dist\WooDesk.dist; normalize to dist\WooDesk
if (Test-Path dist\WooDesk.dist) {
    if (Test-Path dist\WooDesk) { Remove-Item -Recurse -Force dist\WooDesk }
    Move-Item -Path dist\WooDesk.dist -Destination dist\WooDesk
}

Write-Host "==> Standalone app built successfully at: dist\WooDesk\WooDesk.exe"

# Build Inno Setup installer (.exe) if ISCC is available
$isccPath = $null
if (Get-Command iscc -ErrorAction SilentlyContinue) {
    $isccPath = "iscc"
} elseif (Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") {
    $isccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
}

if ($isccPath) {
    Write-Host "==> Compiling installer (.exe) with Inno Setup..."
    & $isccPath packaging\installer.iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE"
    }
    Write-Host "==> Installer created: dist\WooDesk-Setup.exe"
} else {
    Write-Host "==> Notice: Inno Setup (iscc) not found in PATH. Skipping installer compilation."
}
