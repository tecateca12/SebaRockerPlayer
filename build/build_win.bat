@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv" (
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

echo Compilando SebaRockerPlayer (.exe) para Windows...
.venv\Scripts\pyinstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --workpath build_out ^
    --name "SebaRockerPlayer" ^
    --collect-all sounddevice ^
    --collect-all _sounddevice_data ^
    --collect-all soundfile ^
    --collect-all _soundfile_data ^
    --collect-all miniaudio ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.QtWebEngineQuick ^
    --exclude-module PySide6.QtPdf ^
    --exclude-module PySide6.QtPdfWidgets ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQuickWidgets ^
    main.py

echo Compilacion exitosa: dist\SebaRockerPlayer.exe
