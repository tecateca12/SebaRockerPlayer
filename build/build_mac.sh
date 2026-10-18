#!/usr/bin/env bash
set -euo pipefail

# Ir a la raíz del proyecto
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
    --collect-binaries sounddevice \
    --collect-binaries _sounddevice_data \
    --collect-binaries soundfile \
    --collect-binaries _soundfile_data \
    --collect-all miniaudio \
    main.py

echo "✅ Compilación exitosa: dist/SebaRockerPlayer.app"
