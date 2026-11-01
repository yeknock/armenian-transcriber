"""Standalone check for the VAD module (briefs/vad.md): run the Segmenter over WAV files.

Feeds each WAV in 512-sample chunks exactly like live audio, prints every segment (start, end,
length, how long after its end it was handed over), the time per feed() call, and writes each
segment to eval/audio/segments/<wav name>/ so you can listen to the cuts. Run from the repo root:
    python -m scripts.try_vad eval/audio/test_mic.wav
    python -m scripts.try_vad eval/audio/call_speech.wav --timeline
    python -m scripts.try_vad eval/audio/call_speech.wav --min-silence-ms 600 --soft-max-s 6
Input must be 16 kHz mono 16-bit (scripts/record.py writes that). Convert other files with
    ffmpeg -i input.m4a -ar 16000 -ac 1 eval/audio/name.wav
"""
import argparse
import inspect
import resource
import sys
import time
import wave
from pathlib import Path

import numpy as np

from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_CALL, SOURCE_MIC, AudioChunk
from transcriber.vad import CHUNK_SECONDS, Segmenter, _SileroModel

SEGMENTS_DIR = Path("eval/audio/segments")   # inside eval/audio/: git-ignored, never committed
TUNING = ("threshold", "neg_threshold", "min_silence_ms", "pad_ms", "soft_max_s", "min_dip_ms",
          "max_segment_s", "quiet_search_ms", "min_speech_ms")
TIMELINE_WIDTH = 100                           # chunks per line = 3.2 s


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as wav:
        found = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth() * 8)
        if found != (SAMPLE_RATE, 1, 16):
            raise SystemExit(f"error: {path} is {found[0]} Hz, {found[1]} channel(s), {found[2]}-bit; "
                             f"need {SAMPLE_RATE} Hz mono 16-bit. Convert it with:\n"
                             f"  ffmpeg -i {path} -ar {SAMPLE_RATE} -ac 1 {path.with_suffix('.16k.wav')}")
        return np.frombuffer(wav.readframes(wav.getnframes()), "<i2").astype(np.float32) / 32768


def write_wav(path: Path, audio: np.ndarray) -> None:
    """Same format as scripts/record.py (not imported from there: that needs the sound devices)."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(np.round(np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def settings(tuning: dict) -> str:
    """The values the Segmenter really uses: the ones given, else its defaults."""
    defaults = {name: p.default for name, p in inspect.signature(Segmenter).parameters.items()
                if name in TUNING}
    return ", ".join(f"{name}={tuning.get(name, defaults[name])}" for name in TUNING)


def timeline(audio: np.ndarray, segments: list, threshold: float, neg_threshold: float) -> None:
    """One character per chunk: score line ('#' speech, '-' unsure, ' ' silence) and segment line
    (a digit = which segment holds the chunk, counted 1..9 then again from 1)."""
    model = _SileroModel()   # same scores as inside the Segmenter: deterministic, fresh state
    count = len(audio) // CHUNK_SAMPLES
    scores = [model(audio[i * CHUNK_SAMPLES:(i + 1) * CHUNK_SAMPLES]) for i in range(count)]
    marks = [" "] * count
    for n, segment in enumerate(segments):
        first, last = round(segment.start / CHUNK_SECONDS), round(segment.end / CHUNK_SECONDS)
        for i in range(first, last):
            marks[i] = str(n % 9 + 1)
    score_line = "".join("#" if p >= threshold else "-" if p >= neg_threshold else " " for p in scores)
    mark_line = "".join(marks)
    print("  timeline (one character = 32 ms; upper: Silero score, lower: segment number)")
    for k in range(0, count, TIMELINE_WIDTH):
        print(f"  {k * CHUNK_SECONDS:6.1f} s |{score_line[k:k + TIMELINE_WIDTH]}|")
        print(f"           |{mark_line[k:k + TIMELINE_WIDTH]}|")


def run(path: Path, source: str, tuning: dict, show_timeline: bool) -> None:
    audio = read_wav(path)
    count = len(audio) // CHUNK_SAMPLES
    print(f"\n{path}: {len(audio) / SAMPLE_RATE:.2f} s, peak {np.abs(audio).max():.3f}, {count} chunks"
          + (f" ({len(audio) - count * CHUNK_SAMPLES} samples at the end ignored)" if len(audio) % CHUNK_SAMPLES else ""))

    started = time.perf_counter()
    segmenter = Segmenter(source, **tuning)
    load_ms = (time.perf_counter() - started) * 1000
    found, feed_ms = [], []           # found: (segment, file time when it was handed over or None)
    for i in range(count):
        chunk = AudioChunk(source, i * CHUNK_SECONDS, audio[i * CHUNK_SAMPLES:(i + 1) * CHUNK_SAMPLES])
        started = time.perf_counter()
        segments = segmenter.feed(chunk)
        feed_ms.append((time.perf_counter() - started) * 1000)
        found += [(segment, chunk.start + CHUNK_SECONDS) for segment in segments]
    found += [(segment, None) for segment in segmenter.flush()]

    out_dir = SEGMENTS_DIR / path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    old = sorted(out_dir.glob("*.wav"))
    for file in old:                  # files this script wrote last time for the same WAV
        file.unlink()

    print(f"  {'#':>2}  {'start':>8}  {'end':>8}  {'length':>6}  handed over")
    for n, (segment, handed_over) in enumerate(found, start=1):
        name = f"{n:02d}_{segment.start:07.3f}-{segment.end:07.3f}.wav"
        write_wav(out_dir / name, segment.audio)
        when = (f"{handed_over - segment.end:.2f} s after its end" if handed_over is not None
                else "by flush() (the file ended)")
        print(f"  {n:2d}  {segment.start:8.3f}  {segment.end:8.3f}  {segment.end - segment.start:5.2f}s  "
              f"{when:30s} {name}")

    times = np.array(feed_ms[1:]) if len(feed_ms) > 1 else np.array(feed_ms)
    speech = sum(segment.end - segment.start for segment, _ in found)
    print(f"  {len(found)} segment(s), {speech:.1f} s of {len(audio) / SAMPLE_RATE:.1f} s kept, "
          f"dropped_short {segmenter.dropped_short}")
    print(f"  Segmenter load {load_ms:.0f} ms; feed() median {np.median(times):.2f} ms, "
          f"p99 {np.percentile(times, 99):.2f} ms, max {times.max():.2f} ms")
    print(f"  wrote {len(found)} file(s) to {out_dir}/" + (f" (replaced {len(old)} old)" if old else ""))
    if show_timeline:
        timeline(audio, [segment for segment, _ in found],
                 tuning.get("threshold", 0.5), tuning.get("neg_threshold", 0.35))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wavs", nargs="+", type=Path, help="16 kHz mono 16-bit WAV files")
    parser.add_argument("--source", choices=(SOURCE_MIC, SOURCE_CALL), default=SOURCE_MIC,
                        help="label only; it does not change how audio is cut")
    parser.add_argument("--timeline", action="store_true", help="print Silero's score and the segments per chunk")
    for name in TUNING:
        parser.add_argument("--" + name.replace("_", "-"), type=float, help="Segmenter setting (default: its own)")
    args = parser.parse_args()

    tuning = {name: getattr(args, name) for name in TUNING if getattr(args, name) is not None}
    for path in args.wavs:
        if not path.is_file():
            raise SystemExit(f"error: {path} not found")
    try:
        Segmenter(args.source, **tuning)   # bad settings fail here, before any output
    except ValueError as error:
        raise SystemExit(f"error: {error}")
    print(f"Settings: {settings(tuning)}")
    for path in args.wavs:
        run(path, args.source, tuning, args.timeline)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS, KiB on Linux
    peak_mb = peak / 1e6 if sys.platform == "darwin" else peak * 1024 / 1e6
    print(f"\nPeak memory of this process: {peak_mb:.0f} MB (Python + numpy + onnxruntime + Segmenters; "
          f"torch loaded: {'torch' in sys.modules})")


if __name__ == "__main__":
    main()
