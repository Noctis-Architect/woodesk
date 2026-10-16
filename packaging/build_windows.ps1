# Build a self-contained Windows release (all Python dependencies bundled) with PyInstaller
# and an Inno Setup installer (.exe):
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# All prerequisites (Python runtime, PySide6/Qt, keyring, httpx, markdown, assets and the
# dynamic modules) are bundled into dist\WooDesk, so end users do not need Python installed.

param(
    [string]$ServerUrl = $env:WOODESK_SERVER_URL
)

$ErrorActionPreference = "Stop"

Write-Host "==> Installing Python dependencies and PyInstaller..."
python -m pip install -r requirements.txt pyinstaller

if ($ServerUrl) {
    Write-Host "==> Baking in server URL: $ServerUrl"
    # Replace only the default literal so the runtime WOODESK_SERVER_URL override keeps working.
    (Get-Content app\core\config.py -Raw) -replace 'https://woodesk\.wp-hub\.org', $ServerUrl |
        Set-Content app\core\config.py -NoNewline
}

# Clean existing build outputs
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist\WooDesk) { Remove-Item -Recurse -Force dist\WooDesk }
if (Test-Path dist\WooDesk.dist) { Remove-Item -Recurse -Force dist\WooDesk.dist }

Write-Host "==> Compiling standalone Windows build using PyInstaller..."
python -m PyInstaller --noconfirm --clean packaging\woodesk.spec --distpath dist --workpath build

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
