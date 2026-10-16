@echo off
rem One-command setup + launch from source (Windows).
rem
rem   run.bat
rem
rem Creates a virtual environment, installs all prerequisites and starts WooDesk.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ==^> Creating virtual environment in .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment. Is Python 3.10+ installed?
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.deps_installed" (
    echo ==^> Installing prerequisites...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
    type nul > ".venv\.deps_installed"
)

python run.py %*
