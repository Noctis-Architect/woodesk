#!/usr/bin/env bash
# One-command setup + launch from source (Linux / macOS).
#
#   bash run.sh
#
# Creates a virtual environment, installs all prerequisites (works even on distros that
# block system-wide pip installs, e.g. Debian/Ubuntu with PEP 668) and starts WooDesk.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
STAMP="$VENV/.deps_installed"

if [ ! -d "$VENV" ]; then
    echo "==> Creating virtual environment in $VENV..."
    "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    echo "==> Installing prerequisites..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    touch "$STAMP"
fi

exec python run.py "$@"
