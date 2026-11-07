#!/usr/bin/env python3
"""Premium narrator generator for The Red Letters.

Uses an authorized Azure Speech resource to generate real neural audio with
SDK-provided word boundaries. Output matches the existing chapter MP3/JSON
format consumed by the static GitHub Pages reader.

This script never embeds service credentials in the public website.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave

from azure.cognitiveservices import speech as speechsdk

APP = Path(__file__).resolve().parent
HTML = APP / "index.html"
OUTPUT = APP / "audio" / "premium"
VOICES = {
    "british-female": "en-GB-SoniaNeural",
    "british-male": "en-GB-RyanNeural",
    "american-female": "en-US-JennyNeural",
    "american-male": "en-US-GuyNeural",
    "nigerian-female": "en-NG-EzinneNeural",
    "nigerian-male": "en-NG-AbeoNeural",
}
SAMPLE_RATE = 24000


def load_scripture():
    page = HTML.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="scripture-data" type="application/json">([\s\S]*?)</script>',
        page,
    )
    if not match:
        raise RuntimeError("The embedded KJV Gospel data is missing")
    return json.loads(match.group(1))["books"]


def word_timing(text, events, duration_ms):
    spans = list(re.finditer(r"\S+", text))
    if not spans:
        raise RuntimeError("Empty saying")
    known = {}
    for offset, audio_ms, spoken in sorted(events, key=lambda row: row[1]):
        if not spoken.strip() or not any(ch.isalnum() for ch in spoken):
            continue
        i = next((i for i, span in enumerate(spans)
                  if span.start() <= offset < span.end()), -1)
        if i >= 0:
            known.setdefault(i, audio_ms)
    known.setdefault(0, 0)
    anchors = sorted(known)
    result = []
    for i in range(len(spans)):
        if i in known:
            millis = known[i]
        else:
            before = max((x for x in anchors if x < i), default=0)
            after = min((x for x in anchors if x > i), default=len(spans))
            left = known.get(before, 0)
            right = known.get(after, duration_ms)
            millis = left + (right - left) * (i - before) / max(1, after - before)
        result.append(round(min(duration_ms, max(0, millis))))
    for i in range(1, len(result)):
        result[i] = max(result[i], result[i - 1])
    return result


def synthesize(synthesizer, text, voice):
    boundaries = []
    def on_word(event):
        if not event.text:
            return
        boundaries.append((int(event.text_offset),
                           round(event.audio_offset / 10000),
                           str(event.text)))
    synthesizer.synthesis_word_boundary.connect(on_word)
    # A fresh synthesizer is used for each saying so event handlers cannot
    # accidentally accumulate across chapters or verses.
    result = synthesizer.speak_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        details = speechsdk.SpeechSynthesisCancellationDetails.from_result(result)
        raise RuntimeError(f"Azure synthesis canceled for {voice}: {details.reason} / {details.error_details}")
    with wave.open(io.BytesIO(result.audio_data), "rb") as wav:
        if wav.getframerate() != SAMPLE_RATE or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise RuntimeError("Unexpected PCM audio format; expected 24 kHz mono 16 bit")
        frames = wav.readframes(wav.getnframes())
    if not frames:
        raise RuntimeError(f"Azure returned empty audio for {voice}")
    return frames, boundaries


def chapter_audio(book, chapter, voice_key, region, subscription):
    voice = VOICES[voice_key]
    slug = f"{book['n'].lower()}-{chapter['n']:02d}"
    root = OUTPUT / voice_key
    root.mkdir(parents=True, exist_ok=True)
    mp3 = root / f"{slug}.mp3"
    metadata = root / f"{slug}.json"
    if mp3.exists() and metadata.exists() and mp3.stat().st_size > 2000:
        print(f"[premium] skip existing {voice_key} {slug}", flush=True)
        return

    speech_config = speechsdk.SpeechConfig(subscription=subscription, region=region)
    speech_config.speech_synthesis_voice_name = voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    offset_frames, segments = 0, []
    pause = b"\x00\x00" * round(SAMPLE_RATE * .23)
    with tempfile.TemporaryDirectory(prefix="redletters-azure-") as temp:
        wav_file = Path(temp) / "spoken.wav"
        with wave.open(str(wav_file), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            for verse, part, text in chapter["e"]:
                # Fresh synthesizer per verse: no event-handler leakage.
                synthesizer = speechsdk.SpeechSynthesizer(
                    speech_config=speech_config, audio_config=None)
                pcm, events = synthesize(synthesizer, text, voice)
                duration_ms = round(len(pcm) / 2 * 1000 / SAMPLE_RATE)
                start_ms = round(offset_frames * 1000 / SAMPLE_RATE)
                timing = word_timing(text, events, duration_ms)
                if len(timing) != len(text.split()):
                    raise RuntimeError(f"Bad alignment for {slug}:{verse}")
                segments.append({
                    "verse": verse, "part": part,
                    "start_ms": start_ms, "end_ms": start_ms + duration_ms,
                    "words": [start_ms + m for m in timing]
                })
                output.writeframesraw(pcm)
                output.writeframesraw(pause)
                offset_frames += len(pcm) // 2 + len(pause) // 2
            output.writeframes(b"")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
             "-y", "-i", str(wav_file), "-c:a", "libmp3lame",
             "-b:a", "64k", "-ar", str(SAMPLE_RATE), "-ac", "1", str(mp3)],
            check=True)
    if mp3.stat().st_size < 2000:
        raise RuntimeError(f"Empty premium audio: {mp3}")
    record = {
        "version": 1, "voice": voice, "book": book["n"],
        "chapter": chapter["n"],
        "duration_ms": round(offset_frames * 1000 / SAMPLE_RATE),
        "segments": segments
    }
    metadata.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"[premium] {voice_key} {slug} OK ({len(segments)} sayings; {mp3.stat().st_size//1024} KiB)", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--voices", default="british-female,american-female,nigerian-female")
    p.add_argument("--book", default="John")
    p.add_argument("--chapters", default="1")
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        raise RuntimeError("Configure GitHub secrets AZURE_SPEECH_KEY and AZURE_SPEECH_REGION")
    selected = [name.strip() for name in args.voices.split(",")]
    if any(name not in VOICES for name in selected):
        raise RuntimeError(f"Unsupported voice profile in {selected!r}")
    books = load_scripture()
    if args.all:
        work = [(b,c) for b in books for c in b["c"]]
    else:
        wanted = {int(v.strip()) for v in args.chapters.split(",")}
        work = [(b,c) for b in books for c in b["c"]
                if b["n"].lower() == args.book.lower() and c["n"] in wanted]
    if not work:
        raise RuntimeError("No red-letter chapters match selection")
    print(f"[premium] preparing {len(work)} chapters × {len(selected)} natural voices", flush=True)
    for voice in selected:
        for b, chapter in work:
            chapter_audio(b, chapter, voice, region, key)


if __name__ == "__main__":
    main()
