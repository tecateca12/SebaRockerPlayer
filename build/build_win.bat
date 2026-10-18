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
    --collect-binaries sounddevice ^
    --collect-binaries _sounddevice_data ^
    --collect-binaries soundfile ^
    --collect-binaries _soundfile_data ^
    --collect-all miniaudio ^
    main.py

echo Compilacion exitosa: dist\SebaRockerPlayer.exe
pause
