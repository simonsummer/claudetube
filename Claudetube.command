#!/bin/bash
# Claudetube Mac Launcher - double-click to start the web app
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.claudetube/venv"

echo "============================================"
echo "  Claudetube - YouTube Video Analyzer"
echo "============================================"

# Check venv
if [ ! -f "$VENV/bin/python" ]; then
    echo ""
    echo "Erste Installation - richte Umgebung ein..."
    echo ""
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
    echo ""
    echo "Installation abgeschlossen!"
fi

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "FEHLER: ffmpeg nicht gefunden. Installiere mit: brew install ffmpeg"
    read -p "Drücke Enter zum Beenden..."
    exit 1
fi

echo ""
echo "Starte Claudetube im Browser..."
echo "Zum Beenden: Ctrl+C oder Fenster schließen"
echo ""

cd "$SCRIPT_DIR"
"$VENV/bin/streamlit" run app.py --server.headless=false --browser.gatherUsageStats=false
