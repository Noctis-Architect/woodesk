#!/usr/bin/env bash
# Build a self-contained Linux release (all Python dependencies bundled) with PyInstaller.
# Output: dist/WooDesk/WooDesk
#
#   bash packaging/build_linux.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"

# Modern distros (Debian/Ubuntu/Fedora) refuse system-wide pip installs (PEP 668),
# so build inside a virtual environment.
if [ ! -d "$VENV" ]; then
    echo "==> Creating virtual environment in $VENV..."
    "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Installing Python dependencies and PyInstaller..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

echo "==> Cleaning previous build..."
rm -rf build "dist/WooDesk" "dist/WooDesk-linux.tar.gz"

echo "==> Building with PyInstaller..."
python -m PyInstaller --noconfirm --clean packaging/woodesk.spec --distpath dist --workpath build

echo "==> Packaging portable archive..."
tar -C dist -czf "dist/WooDesk-linux.tar.gz" WooDesk

echo "==> Done:"
echo "    Portable folder : dist/WooDesk/WooDesk"
echo "    Portable archive: dist/WooDesk-linux.tar.gz"
