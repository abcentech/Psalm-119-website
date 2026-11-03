#!/usr/bin/env python3
"""Build real, offline neural narration with Kokoro and precise clip boundaries.

Outputs per-chapter MP3 and sidecar timings for the Red Letters web reader.
Use only licensed Kokoro model (Apache-2.0). No end-user API key required.
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "words-of-christ" / "index.html"
AUDIO = ROOT / "words-of-christ" / "audio"
VOICE_MAP = {
    "british": ("bf_emma", "en-gb"),
    "american": ("af_heart", "en-us"),
}


def text_data():
    page = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="scripture-data" type="application/json">(.*?)</script>',
        page,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError("The embedded gospel dataset cannot be found")
    return json.loads(match.group(1))


def build_word_starts(words, phonemes, duration):
    """Use model phoneme word groups; interpolate only mismatched groups."""
    if not words:
        return []
    groups = []
    for p in phonemes:
        phoneme = str(getattr(p, "phoneme", ""))
        start = float(getattr(p, "start", 0.0))
        if phoneme.isspace():
            continue
        if not groups or groups[-1][1]:
            groups.append([start, False])
        # The next non-space starts a new group after a whitespace phoneme.
        groups[-1][1] = False

    # Group phonemes on explicit space boundaries.
    boundaries = []
    next_word = True
    for p in phonemes:
        ph = str(getattr(p, "phoneme", ""))
        if ph == " " or ph.isspace():
            next_word = True
        elif next_word:
            boundaries.append(float(getattr(p, "start", 0.0)))
            next_word = False

    if len(boundaries) == len(words):
        return [max(0, min(duration, int(t * 1000))) for t in boundaries]
    if len(boundaries) > 1:
        scaled = []
        for i in range(len(words)):
            pos = i * (len(boundaries) - 1) / max(1, len(words) - 1)
            left = int(math.floor(pos))
            right = min(len(boundaries) - 1, left + 1)
            t = boundaries[left] + (boundaries[right] - boundaries[left]) * (pos - left)
            scaled.append(max(0, min(duration, round(1000 * t))))
        return scaled

    # Last-resort duration-based estimate if phoneme timing is unavailable.
    width = sum(max(1, len(w)) for w in words)
    cursor, starts = 0, []
    for word in words:
        starts.append(round(duration * cursor / width))
        cursor += max(1, len(word))
    return starts


def generate(model, voice_id, lang, book, chapter, output_root):
    label = book["n"]
    c = chapter["n"]
    slug = f"{label.lower()}-{c:02d}"
    target = output_root / f"{slug}.mp3"
    sidecar = output_root / f"{slug}.json"
    output_root.mkdir(parents=True, exist_ok=True)
    print(f"[neural] generating {voice_id} {label} {c}, {len(chapter['e'])} sayings", flush=True)

    frames = 0
    timings = []
    rate = 24000
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / f"{slug}.wav"
        with wave.open(str(wav_path), "wb") as audiofile:
            audiofile.setnchannels(1)
            audiofile.setsampwidth(2)
            audiofile.setframerate(rate)
            for entry in chapter["e"]:
                verse, part, text = entry
                words = text.strip().split()
                if not words:
                    raise RuntimeError(f"Empty saying in {slug}:{verse}")
                signal, sr, phones = model.create_timed(
                    text, voice=voice_id, speed=0.95, lang=lang
                )
                if sr != rate or len(signal) < 1000:
                    raise RuntimeError(f"Invalid audio in {slug}:{verse}: {sr}/{len(signal)}")
                start_ms = round(frames * 1000 / rate)
                duration_ms = round(len(signal) * 1000 / rate)
                word_offsets = build_word_starts(words, phones, duration_ms)
                if len(word_offsets) != len(words):
                    raise RuntimeError(f"Bad word alignment for {slug}:{verse}")
                timings.append({
                    "verse": verse, "part": part, "start_ms": start_ms,
                    "end_ms": start_ms + duration_ms,
                    "words": [start_ms + t for t in word_offsets],
                })
                clipped = (np.clip(signal, -1, 1) * 32767).astype("<i2")
                audiofile.writeframes(clipped.tobytes())
                frames += len(signal)
                silence = int(rate * 0.2)
                audiofile.writeframes(b"\x00\x00" * silence)
                frames += silence

        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
             "-y", "-i", str(wav_path), "-c:a", "libmp3lame",
             "-ar", "24000", "-ac", "1", "-b:a", "48k", str(target)],
            check=True,
        )

    if target.stat().st_size < 1000:
        raise RuntimeError(f"Empty output MP3: {target}")
    output = {
        "version": 1,
        "voice": voice_id,
        "book": label,
        "chapter": c,
        "duration_ms": round(frames * 1000 / rate),
        "segments": timings,
    }
    sidecar.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(f"[neural] OK {target.relative_to(ROOT)} {target.stat().st_size // 1024} KiB", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--voices", required=True)
    parser.add_argument("--chapters", default="John:1,John:3")
    parser.add_argument("--output", default=str(AUDIO))
    args = parser.parse_args()
    data = text_data()
    desired = set(args.chapters.split(","))
    requested = [x.strip() for x in args.voices.split(",")]
    if any(x not in VOICE_MAP for x in requested):
        raise RuntimeError(f"Unknown voice: {requested}")
    model = Kokoro(args.model, str(Path(args.model).parent / "voices-v1.0.bin"))
    try:
        if not model.has_timings:
            raise RuntimeError("The selected Kokoro model does not provide timestamps")
        generated = 0
        for label in requested:
            voice, lang = VOICE_MAP[label]
            for b in data["books"]:
                for chapter in b["c"]:
                    if f"{b['n']}:{chapter['n']}" in desired:
                        generate(model, voice, lang, b, chapter, Path(args.output) / label)
                        generated += 1
        if generated != len(desired) * len(requested):
            raise RuntimeError(f"Expected {len(desired) * len(requested)} files; made {generated}")
    finally:
        model.voices.close()


if __name__ == "__main__":
    main()
