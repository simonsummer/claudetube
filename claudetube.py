#!/usr/bin/env python3
"""
Claudetube - YouTube Video Analyzer for Claude
Downloads, slices, transcribes and extracts frames from YouTube videos
so Claude can analyze both speech and visual content.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ts_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS or MM:SS or seconds string to float seconds."""
    parts = ts.strip().split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def seconds_to_ts(s: float) -> str:
    """Convert seconds to HH:MM:SS string."""
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def format_frame_name(s: float) -> str:
    """Create a filename-safe timestamp like frame_05m30s.jpg"""
    m = int(s // 60)
    sec = int(s % 60)
    return f"frame_{m:03d}m{sec:02d}s.jpg"


def _ensure_path():
    """Ensure homebrew tools are in PATH."""
    homebrew = "/opt/homebrew/bin"
    if homebrew not in os.environ.get("PATH", ""):
        os.environ["PATH"] = homebrew + os.pathsep + os.environ.get("PATH", "")


def run_cmd(cmd, desc="", timeout=3600):
    """Run a shell command and return stdout. Raises on failure."""
    _ensure_path()
    if desc:
        print(f"  {desc}...")
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:500]}", file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd[:3])}...")
    return result.stdout


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def fetch_metadata(url: str, output_dir: Path) -> dict:
    """Download video metadata via yt-dlp."""
    print("[1/4] Fetching metadata...")
    raw = run_cmd(
        ["yt-dlp", "--dump-json", "--no-download", url],
        desc="Downloading video info"
    )
    info = json.loads(raw)
    meta = {
        "id": info.get("id", "unknown"),
        "title": info.get("title", ""),
        "channel": info.get("channel", info.get("uploader", "")),
        "upload_date": info.get("upload_date", ""),
        "duration": info.get("duration", 0),
        "duration_string": info.get("duration_string", ""),
        "description": info.get("description", ""),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "tags": info.get("tags", []),
        "categories": info.get("categories", []),
        "url": url,
        "has_subtitles": bool(info.get("subtitles")),
        "has_auto_captions": bool(info.get("automatic_captions")),
        "language": info.get("language", ""),
    }
    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"  Title: {meta['title']}")
    print(f"  Duration: {meta['duration_string']} ({meta['duration']}s)")
    return meta


def download_audio(url: str, output_dir: Path, start: str = None, end: str = None) -> Path:
    """Download audio track from YouTube video."""
    print("[2/4] Downloading audio...")
    audio_path = output_dir / "audio.mp3"

    # Download full audio first
    tmp_audio = output_dir / "audio_full.mp3"
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", str(tmp_audio),
        "--no-playlist",
        url,
    ]
    run_cmd(cmd, desc="Extracting audio")

    # If slicing requested, use ffmpeg to cut
    if start or end:
        print(f"  Slicing audio: {start or '00:00:00'} -> {end or 'end'}...")
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(tmp_audio)]
        if start:
            ffmpeg_cmd += ["-ss", start]
        if end:
            ffmpeg_cmd += ["-to", end]
        ffmpeg_cmd += ["-c", "copy", str(audio_path)]
        run_cmd(ffmpeg_cmd, desc="Cutting audio segment")
        tmp_audio.unlink(missing_ok=True)
    else:
        tmp_audio.rename(audio_path)

    print(f"  Audio saved: {audio_path}")
    return audio_path


def try_youtube_subtitles(url: str, output_dir: Path, lang: str = None) -> Optional[Path]:
    """Try to download YouTube's own subtitles/auto-captions."""
    print("  Trying YouTube subtitles...")
    sub_path = output_dir / "yt_subs"

    # Try manual subtitles first, then auto-captions
    for flag in ["--write-subs", "--write-auto-subs"]:
        cmd = [
            "yt-dlp",
            flag,
            "--sub-format", "json3",
            "--sub-langs", lang or "en,de,fr,es",
            "--skip-download",
            "-o", str(sub_path),
            "--no-playlist",
            url,
        ]
        try:
            run_cmd(cmd, desc=f"Fetching subtitles ({flag})")
        except RuntimeError:
            continue

        # Find any downloaded subtitle file
        for f in output_dir.glob("yt_subs*.json3"):
            return f

    return None


def parse_youtube_subs(sub_file: Path, start_sec: float = 0, end_sec: float = None) -> List[Dict]:
    """Parse YouTube JSON3 subtitle format into segments."""
    data = json.loads(sub_file.read_text())
    events = data.get("events", [])
    segments = []
    for ev in events:
        t_start = ev.get("tStartMs", 0) / 1000.0
        dur = ev.get("dDurationMs", 0) / 1000.0
        segs = ev.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        text = text.replace("\n", " ")
        if not text:
            continue
        if start_sec and t_start < start_sec:
            continue
        if end_sec and t_start > end_sec:
            break
        segments.append({
            "start": round(t_start, 2),
            "end": round(t_start + dur, 2),
            "text": text,
        })
    return segments


def split_audio(audio_path: Path, chunk_minutes: int = 10) -> List[Path]:
    """Split audio into chunks for faster transcription."""
    duration_cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
    ]
    duration = float(run_cmd(duration_cmd).strip())
    chunk_seconds = chunk_minutes * 60

    if duration <= chunk_seconds * 1.5:
        return [audio_path]

    chunks = []
    start = 0
    i = 0
    while start < duration:
        chunk_path = audio_path.parent / f"chunk_{i:03d}.mp3"
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ss", str(start), "-t", str(chunk_seconds),
            "-c", "copy", str(chunk_path)
        ]
        run_cmd(cmd)
        chunks.append(chunk_path)
        start += chunk_seconds
        i += 1

    print(f"  Split audio into {len(chunks)} chunks of {chunk_minutes} min")
    return chunks


def transcribe_whisper(audio_path: Path, model_name: str = "base", language: str = None) -> List[Dict]:
    """Transcribe audio using mlx-whisper (Apple Silicon) with fallback to OpenAI Whisper."""
    mlx_models = {
        "tiny": "mlx-community/whisper-tiny-mlx",
        "base": "mlx-community/whisper-base-mlx",
        "small": "mlx-community/whisper-small-mlx",
        "medium": "mlx-community/whisper-medium-mlx",
        "large": "mlx-community/whisper-large-v3-mlx",
    }

    # Split long audio into chunks
    chunks = split_audio(audio_path)

    try:
        import mlx_whisper
        use_mlx = True
        model_path = mlx_models.get(model_name, mlx_models["base"])
        print(f"  Using mlx-whisper ({model_name} model, Apple Silicon accelerated)...")
    except ImportError:
        use_mlx = False
        import whisper
        print(f"  Using OpenAI Whisper ({model_name})...")
        model = whisper.load_model(model_name)

    all_segments = []
    for ci, chunk_path in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  Chunk {ci + 1}/{len(chunks)}...")

        if use_mlx:
            options = {"path_or_hf_repo": model_path}
            if language:
                options["language"] = language
            result = mlx_whisper.transcribe(str(chunk_path), **options)
        else:
            options = {}
            if language:
                options["language"] = language
            result = model.transcribe(str(chunk_path), **options)

        # Calculate time offset for this chunk
        offset = 0.0
        if len(chunks) > 1 and ci > 0:
            offset = ci * 10 * 60  # chunk_minutes = 10

        for seg in result.get("segments", []):
            all_segments.append({
                "start": round(seg["start"] + offset, 2),
                "end": round(seg["end"] + offset, 2),
                "text": seg["text"].strip(),
            })

    # Clean up chunk files
    for chunk_path in chunks:
        if chunk_path != audio_path:
            chunk_path.unlink(missing_ok=True)

    return all_segments


def create_transcript(
    url: str,
    audio_path: Path,
    output_dir: Path,
    whisper_model: str = "base",
    language: str = None,
    start: str = None,
    end: str = None,
    force_whisper: bool = False,
) -> Path:
    """Create transcript - tries YouTube subs first, falls back to Whisper."""
    print("[3/4] Creating transcript...")

    segments = None
    source = None
    start_sec = ts_to_seconds(start) if start else 0
    end_sec = ts_to_seconds(end) if end else None

    # Strategy 1: YouTube subtitles (fast, no compute)
    if not force_whisper:
        sub_file = try_youtube_subtitles(url, output_dir, language)
        if sub_file:
            segments = parse_youtube_subs(sub_file, start_sec, end_sec)
            if segments:
                source = "youtube_subtitles"
                print(f"  Got {len(segments)} segments from YouTube subtitles")
                # Clean up subtitle files
                for f in output_dir.glob("yt_subs*"):
                    f.unlink(missing_ok=True)

    # Strategy 2: Whisper (local transcription)
    if not segments:
        print("  No YouTube subtitles found, using Whisper...")
        segments = transcribe_whisper(audio_path, whisper_model, language)
        source = f"whisper_{whisper_model}"
        print(f"  Transcribed {len(segments)} segments with Whisper")

    # Save JSON transcript (with timestamps)
    transcript_json = output_dir / "transcript.json"
    transcript_data = {
        "source": source,
        "segments": segments,
    }
    transcript_json.write_text(
        json.dumps(transcript_data, indent=2, ensure_ascii=False)
    )

    # Save plain text transcript (readable)
    transcript_txt = output_dir / "transcript.txt"
    lines = []
    for seg in segments:
        ts = seconds_to_ts(seg["start"])
        lines.append(f"[{ts}] {seg['text']}")
    transcript_txt.write_text("\n".join(lines), encoding="utf-8")

    print(f"  Transcript saved: {transcript_txt}")
    return transcript_txt


def extract_frames(
    url: str,
    output_dir: Path,
    interval: int = 30,
    start: str = None,
    end: str = None,
    max_frames: int = 600,
) -> List[Path]:
    """Extract frames from video at regular intervals using yt-dlp + ffmpeg."""
    print("[4/4] Extracting frames...")
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # Download video (best quality for readable frames)
    video_path = output_dir / "video_tmp.mp4"
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "-o", str(video_path),
        "--no-playlist",
        url,
    ]
    run_cmd(cmd, desc="Downloading video (best quality for frames)")

    # Build ffmpeg command for frame extraction
    ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    if start:
        ffmpeg_cmd += ["-ss", start]
    if end:
        ffmpeg_cmd += ["-to", end]

    # Extract one frame every N seconds
    ffmpeg_cmd += [
        "-vf", f"fps=1/{interval}",
        "-qscale:v", "2",
        "-frames:v", str(max_frames),
        str(frames_dir / "frame_%04d.jpg"),
    ]
    run_cmd(ffmpeg_cmd, desc=f"Extracting frames every {interval}s")

    # Rename frames with timestamps
    start_sec = ts_to_seconds(start) if start else 0
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    renamed = []
    for i, f in enumerate(frame_files):
        t = start_sec + i * interval
        new_name = frames_dir / format_frame_name(t)
        f.rename(new_name)
        renamed.append(new_name)

    # Clean up video
    video_path.unlink(missing_ok=True)

    print(f"  Extracted {len(renamed)} frames to {frames_dir}/")
    return renamed


def write_summary(output_dir: Path, meta: dict, frame_paths: List[Path]):
    """Write a summary file that tells Claude what's available."""
    summary_lines = [
        "=" * 60,
        "CLAUDETUBE ANALYSIS PACKAGE",
        "=" * 60,
        "",
        f"Video: {meta.get('title', 'Unknown')}",
        f"Channel: {meta.get('channel', 'Unknown')}",
        f"Duration: {meta.get('duration_string', '?')}",
        f"Upload: {meta.get('upload_date', '?')}",
        "",
        "--- FILES ---",
        f"Metadata:   {output_dir}/metadata.json",
        f"Transcript: {output_dir}/transcript.txt  (timestamped plain text)",
        f"Transcript: {output_dir}/transcript.json (structured with timestamps)",
        "",
        "--- FRAMES ---",
    ]
    for fp in frame_paths:
        t_match = re.search(r"(\d+)m(\d+)s", fp.name)
        if t_match:
            m, s = int(t_match.group(1)), int(t_match.group(2))
            summary_lines.append(f"  [{m:02d}:{s:02d}] {fp}")
    summary_lines += [
        "",
        "--- HOW TO USE ---",
        "1. Read transcript.txt for what was SAID",
        "2. Read individual frame images for what was SHOWN",
        "3. Read metadata.json for video context",
        "=" * 60,
    ]
    summary_path = output_dir / "summary.txt"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    return summary_path


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def _resolve_language(args_lang: Optional[str], meta: dict) -> Optional[str]:
    """Resolve language: explicit flag > YouTube metadata > None (auto-detect)."""
    if args_lang:
        return args_lang
    yt_lang = meta.get("language")
    if yt_lang:
        print(f"  Auto-detected language from YouTube: {yt_lang}")
        return yt_lang
    return None


def cmd_analyze(args):
    """Full analysis pipeline: metadata + transcript + frames."""
    output_dir = setup_output_dir(args.url, args.output_dir)

    meta = fetch_metadata(args.url, output_dir)
    language = _resolve_language(args.lang, meta)
    audio_path = download_audio(args.url, output_dir, args.start, args.end)
    create_transcript(
        args.url, audio_path, output_dir,
        whisper_model=args.whisper_model,
        language=language,
        start=args.start, end=args.end,
        force_whisper=args.force_whisper,
    )
    frame_paths = extract_frames(
        args.url, output_dir,
        interval=args.frame_interval,
        start=args.start, end=args.end,
        max_frames=args.max_frames,
    )
    summary_path = write_summary(output_dir, meta, frame_paths)

    print()
    print("=" * 60)
    print("DONE! Analysis package ready.")
    print(f"Output: {output_dir}")
    print(f"Summary: {summary_path}")
    print("=" * 60)
    # Print summary for Claude to read
    print()
    print(summary_path.read_text())


def cmd_transcribe(args):
    """Transcribe only."""
    output_dir = setup_output_dir(args.url, args.output_dir)
    meta = fetch_metadata(args.url, output_dir)
    language = _resolve_language(args.lang, meta)
    audio_path = download_audio(args.url, output_dir, args.start, args.end)
    create_transcript(
        args.url, audio_path, output_dir,
        whisper_model=args.whisper_model,
        language=language,
        start=args.start, end=args.end,
        force_whisper=args.force_whisper,
    )
    print(f"\nDone! Transcript in {output_dir}/")


def cmd_frames(args):
    """Extract frames only."""
    output_dir = setup_output_dir(args.url, args.output_dir)
    meta = fetch_metadata(args.url, output_dir)
    frame_paths = extract_frames(
        args.url, output_dir,
        interval=args.frame_interval,
        start=args.start, end=args.end,
        max_frames=args.max_frames,
    )
    print(f"\nDone! {len(frame_paths)} frames in {output_dir}/frames/")


def cmd_download(args):
    """Download audio only."""
    output_dir = setup_output_dir(args.url, args.output_dir)
    meta = fetch_metadata(args.url, output_dir)
    audio_path = download_audio(args.url, output_dir, args.start, args.end)
    print(f"\nDone! Audio: {audio_path}")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def get_video_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    # Fallback: hash the URL
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:11]


def setup_output_dir(url: str, base_dir: str = None) -> Path:
    """Create output directory for this video."""
    vid = get_video_id(url)
    base = Path(base_dir) if base_dir else Path("output")
    out = base / vid
    out.mkdir(parents=True, exist_ok=True)
    (out / "frames").mkdir(exist_ok=True)
    return out


def main():
    parser = argparse.ArgumentParser(
        prog="claudetube",
        description="YouTube Video Analyzer for Claude - analyze videos via speech and vision",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Common arguments
    def add_common_args(p):
        p.add_argument("url", help="YouTube video URL")
        p.add_argument("--start", help="Start time (HH:MM:SS or MM:SS)")
        p.add_argument("--end", help="End time (HH:MM:SS or MM:SS)")
        p.add_argument("--output-dir", "-o", help="Output directory (default: ./output)")
        p.add_argument("--lang", help="Language hint (e.g. 'de', 'en')")

    # analyze command
    p_analyze = subparsers.add_parser("analyze", help="Full analysis: transcript + frames")
    add_common_args(p_analyze)
    p_analyze.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    p_analyze.add_argument("--force-whisper", action="store_true", help="Skip YouTube subs, use Whisper")
    p_analyze.add_argument("--frame-interval", type=int, default=30, help="Seconds between frames (default: 30)")
    p_analyze.add_argument("--max-frames", type=int, default=600, help="Max frames to extract (default: 600)")
    p_analyze.set_defaults(func=cmd_analyze)

    # transcribe command
    p_trans = subparsers.add_parser("transcribe", help="Transcribe video audio")
    add_common_args(p_trans)
    p_trans.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    p_trans.add_argument("--force-whisper", action="store_true")
    p_trans.set_defaults(func=cmd_transcribe)

    # frames command
    p_frames = subparsers.add_parser("frames", help="Extract video frames")
    add_common_args(p_frames)
    p_frames.add_argument("--frame-interval", type=int, default=30, help="Seconds between frames (default: 30)")
    p_frames.add_argument("--max-frames", type=int, default=600)
    p_frames.set_defaults(func=cmd_frames)

    # download command
    p_dl = subparsers.add_parser("download", help="Download audio only")
    add_common_args(p_dl)
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
