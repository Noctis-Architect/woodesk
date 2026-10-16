# Build a Windows folder-app with PyInstaller:  powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# Optional: $env:WOODESK_SERVER_URL = "https://api.example.com"  (baked in as the default server)
python -m pip install -r requirements.txt pyinstaller
if ($env:WOODESK_SERVER_URL) { (Get-Content app\core\config.py) -replace 'os.environ.get\("WOODESK_SERVER_URL", ""\)', "`"$env:WOODESK_SERVER_URL`"" | Set-Content app\core\config.py }
pyinstaller --noconfirm --windowed --name WooDesk `
  --add-data "app/assets;app/assets" `
  --hidden-import keyring.backends.Windows `
  run.py
Write-Host "Done: dist\WooDesk\WooDesk.exe  (build the installer with Inno Setup: packaging\installer.iss)"
