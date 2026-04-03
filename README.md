# Claudetube

YouTube Video Analyzer — extrahiert **Transkripte** (Sprache) und **Frames** (Bild) aus YouTube-Videos, damit Claude sie vollständig analysieren kann.

## Features

- **Transkription** — Nutzt YouTube-Untertitel oder lokales Whisper-Modell
- **Frame-Extraktion** — Screenshots in regelmäßigen Abständen
- **Video-Slicing** — Nur bestimmte Zeitbereiche analysieren
- **Web-UI** — Streamlit-App zum Starten per Doppelklick
- **CLI** — Kommandozeile für Claude-Integration

## Voraussetzungen

- Python 3.8+
- ffmpeg (`brew install ffmpeg`)
- yt-dlp (`brew install yt-dlp`)

## Installation

```bash
git clone https://github.com/simonstummer/claudetube.git
cd claudetube
./setup.sh
```

## Nutzung

### Web-App (Mac)

Doppelklick auf `Claudetube.command` — öffnet die App im Browser.

### CLI (für Claude)

```bash
# Komplett-Analyse (Transkript + Frames)
./ct analyze "https://www.youtube.com/watch?v=VIDEO_ID"

# Nur Transkript
./ct transcribe "https://www.youtube.com/watch?v=VIDEO_ID"

# Nur Frames
./ct frames "https://www.youtube.com/watch?v=VIDEO_ID"

# Mit Zeitbereich
./ct analyze "https://www.youtube.com/watch?v=VIDEO_ID" --start 05:00 --end 10:00

# Deutsches Video mit Whisper
./ct transcribe "https://www.youtube.com/watch?v=VIDEO_ID" --lang de --force-whisper
```

### Optionen

| Option | Beschreibung | Default |
|--------|-------------|---------|
| `--start` | Startzeit (HH:MM:SS) | Anfang |
| `--end` | Endzeit (HH:MM:SS) | Ende |
| `--frame-interval` | Sekunden zwischen Frames | 30 |
| `--max-frames` | Maximale Frame-Anzahl | 60 |
| `--whisper-model` | tiny/base/small/medium/large | base |
| `--force-whisper` | Whisper statt YT-Untertitel | false |
| `--lang` | Sprachhinweis (de, en, ...) | auto |

## Output-Struktur

```
output/<video-id>/
├── metadata.json       # Video-Metadaten
├── transcript.txt      # Transkript mit Zeitstempeln
├── transcript.json     # Strukturiertes Transkript
├── audio.mp3           # Extrahiertes Audio
├── summary.txt         # Übersicht für Claude
└── frames/
    ├── frame_000m00s.jpg
    ├── frame_000m30s.jpg
    └── ...
```

## Tech Stack

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Video/Audio-Download
- [OpenAI Whisper](https://github.com/openai/whisper) — Lokale Transkription
- [ffmpeg](https://ffmpeg.org/) — Audio/Video-Processing
- [Streamlit](https://streamlit.io/) — Web-UI

## Lizenz

MIT
