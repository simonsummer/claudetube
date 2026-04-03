#!/usr/bin/env python3
"""
Claudetube - Streamlit Web UI
YouTube Video Analyzer for Claude: speech + vision analysis
"""

import json
import os
import streamlit as st
from pathlib import Path

from claudetube import (
    fetch_metadata,
    download_audio,
    create_transcript,
    extract_frames,
    write_summary,
    setup_output_dir,
    get_video_id,
    seconds_to_ts,
)

st.set_page_config(
    page_title="Claudetube",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 Claudetube")
st.caption("YouTube Video Analyzer — Transkript + Frames für Claude-Analyse")

# --- Sidebar Settings ---
with st.sidebar:
    st.header("Einstellungen")
    frame_interval = st.slider("Frame-Intervall (Sekunden)", 5, 300, 60)
    max_frames = st.slider("Max. Frames", 5, 500, 200)
    whisper_model = st.selectbox("Whisper-Modell", ["tiny", "base", "small", "medium", "large"], index=1)
    force_whisper = st.checkbox("Whisper erzwingen (keine YT-Untertitel)")
    lang = st.text_input("Sprache (z.B. 'de', 'en')", value="")

    st.divider()
    st.caption("Claudetube v1.0")
    st.caption("Venv: ~/.claudetube/venv")

# --- Main Input ---
url = st.text_input("YouTube URL eingeben:", placeholder="https://www.youtube.com/watch?v=...")

col_start, col_end = st.columns(2)
with col_start:
    start_time = st.text_input("Startzeit (optional)", placeholder="00:05:00")
with col_end:
    end_time = st.text_input("Endzeit (optional)", placeholder="00:10:00")

# --- Action Buttons ---
col_a, col_b, col_c = st.columns(3)
with col_a:
    do_analyze = st.button("🔍 Komplett-Analyse", type="primary", use_container_width=True)
with col_b:
    do_transcribe = st.button("📝 Nur Transkript", use_container_width=True)
with col_c:
    do_frames = st.button("🖼️ Nur Frames", use_container_width=True)

# --- Processing ---
if (do_analyze or do_transcribe or do_frames) and url:
    start = start_time.strip() or None
    end = end_time.strip() or None
    language = lang.strip() or None

    output_dir = setup_output_dir(url)

    # Step 1: Metadata
    with st.status("Video-Infos laden...", expanded=True) as status:
        try:
            meta = fetch_metadata(url, output_dir)
        except Exception as e:
            st.error(f"Fehler beim Laden der Video-Infos: {e}")
            st.stop()

        st.write(f"**{meta['title']}**")
        st.write(f"Kanal: {meta['channel']} | Dauer: {meta['duration_string']} | Upload: {meta['upload_date']}")
        status.update(label="Video-Infos geladen", state="complete")

    # Step 2: Transcript
    if do_analyze or do_transcribe:
        with st.status("Transkript erstellen...", expanded=True) as status:
            try:
                audio_path = download_audio(url, output_dir, start, end)
                st.write("Audio heruntergeladen")
                transcript_path = create_transcript(
                    url, audio_path, output_dir,
                    whisper_model=whisper_model,
                    language=language,
                    start=start, end=end,
                    force_whisper=force_whisper,
                )
                st.write("Transkript erstellt")
                status.update(label="Transkript fertig", state="complete")
            except Exception as e:
                st.error(f"Fehler bei Transkription: {e}")
                status.update(label="Transkript fehlgeschlagen", state="error")

    # Step 3: Frames
    frame_paths = []
    if do_analyze or do_frames:
        with st.status("Frames extrahieren...", expanded=True) as status:
            try:
                if not (do_analyze or do_transcribe):
                    # Need audio download for frames-only mode too? No, just download video
                    pass
                frame_paths = extract_frames(
                    url, output_dir,
                    interval=frame_interval,
                    start=start, end=end,
                    max_frames=max_frames,
                )
                st.write(f"{len(frame_paths)} Frames extrahiert")
                status.update(label=f"{len(frame_paths)} Frames extrahiert", state="complete")
            except Exception as e:
                st.error(f"Fehler bei Frame-Extraktion: {e}")
                status.update(label="Frames fehlgeschlagen", state="error")

    # --- Results ---
    st.divider()
    st.header("Ergebnisse")

    # Metadata
    with st.expander("📋 Video-Metadaten", expanded=False):
        st.json(meta)

    # Transcript
    transcript_txt = output_dir / "transcript.txt"
    if transcript_txt.exists():
        with st.expander("📝 Transkript", expanded=True):
            content = transcript_txt.read_text(encoding="utf-8")
            st.text_area("Transkript", content, height=400)

            # Download button
            st.download_button(
                "Transkript herunterladen (.txt)",
                content,
                file_name=f"{get_video_id(url)}_transcript.txt",
                mime="text/plain",
            )

    # Frames
    if frame_paths:
        with st.expander("🖼️ Frames", expanded=True):
            cols = st.columns(4)
            for i, fp in enumerate(frame_paths):
                with cols[i % 4]:
                    import re
                    t_match = re.search(r"(\d+)m(\d+)s", fp.name)
                    label = fp.name
                    if t_match:
                        m, s = int(t_match.group(1)), int(t_match.group(2))
                        label = f"{m:02d}:{s:02d}"
                    st.image(str(fp), caption=label, use_container_width=True)

    # Output path info
    st.divider()
    st.info(f"📁 Alle Dateien gespeichert in: `{output_dir.resolve()}`")

    # Write summary for Claude
    if do_analyze:
        write_summary(output_dir, meta, frame_paths)

elif (do_analyze or do_transcribe or do_frames) and not url:
    st.warning("Bitte eine YouTube-URL eingeben.")

# --- Previous analyses ---
output_base = Path("output")
if output_base.exists():
    dirs = sorted([d for d in output_base.iterdir() if d.is_dir()], reverse=True)
    if dirs:
        st.divider()
        with st.expander(f"📂 Frühere Analysen ({len(dirs)})", expanded=False):
            for d in dirs:
                meta_file = d / "metadata.json"
                if meta_file.exists():
                    m = json.loads(meta_file.read_text())
                    st.write(f"**{m.get('title', d.name)}** — {m.get('channel', '?')} — `{d.name}`")
                else:
                    st.write(f"`{d.name}`")
