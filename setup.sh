#!/bin/bash
# Claudetube Setup Script
set -e

VENV="$HOME/.claudetube/venv"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Claudetube Setup"
echo "================"

# Check prerequisites
echo "Prüfe Voraussetzungen..."

if ! command -v python3 &> /dev/null; then
    echo "FEHLER: python3 nicht gefunden"
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "FEHLER: ffmpeg nicht gefunden. Installiere mit: brew install ffmpeg"
    exit 1
fi

if ! command -v yt-dlp &> /dev/null; then
    echo "Installiere yt-dlp..."
    brew install yt-dlp
fi

echo "OK"

# Create venv
echo ""
echo "Erstelle Python-Umgebung in $VENV ..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "============================================"
echo "  Setup abgeschlossen!"
echo ""
echo "  App starten:    Doppelklick auf Claudetube.command"
echo "  CLI nutzen:     ./ct analyze <youtube-url>"
echo "============================================"
