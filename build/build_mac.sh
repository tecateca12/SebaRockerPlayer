#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "Compilando SebaRockerPlayer (.app) para macOS..."
.venv/bin/pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --workpath build_out \
    --name "SebaRockerPlayer" \
    --collect-all sounddevice \
    --collect-all _sounddevice_data \
    --collect-all soundfile \
    --collect-all _soundfile_data \
    --collect-all miniaudio \
    --exclude-module PySide6.QtWebEngineCore \
    --exclude-module PySide6.QtWebEngineWidgets \
    --exclude-module PySide6.QtWebEngineQuick \
    --exclude-module PySide6.QtPdf \
    --exclude-module PySide6.QtPdfWidgets \
    --exclude-module PySide6.QtQml \
    --exclude-module PySide6.QtQuick \
    --exclude-module PySide6.QtQuickWidgets \
    main.py

echo "✅ Compilación exitosa: dist/SebaRockerPlayer.app"
