"""Standalone check for the ASR module (briefs/asr.md): transcribe WAV files and time it.

Prints load time and peak memory at start, then for each file: the Armenian text, the audio length,
the processing time and the real-time factor (processing time / audio length; < 1 = faster than real time).
A folder is read as all its WAVs in name order, e.g. the VAD's cuts in eval/audio/segments/<name>/,
which is exactly what ASR gets live. Run from the repo root:
    python -m scripts.try_asr eval/audio/test_mic.wav eval/audio/call_speech.wav
    python -m scripts.try_asr eval/audio/segments/call_interview --threads 2 --repeat 3
Input must be 16 kHz mono 16-bit (scripts/record.py writes that).
"""
import argparse
import resource
import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

from transcriber.contracts import SAMPLE_RATE


def read_wav(path: Path) -> np.ndarray:
    """Same reader as scripts/try_vad.py (not imported: that would load the VAD too)."""
    with wave.open(str(path)) as wav:
        found = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth() * 8)
        if found != (SAMPLE_RATE, 1, 16):
            raise SystemExit(f"error: {path} is {found[0]} Hz, {found[1]} channel(s), {found[2]}-bit; "
                             f"need {SAMPLE_RATE} Hz mono 16-bit. Convert it with:\n"
                             f"  ffmpeg -i {path} -ar {SAMPLE_RATE} -ac 1 {path.with_suffix('.16k.wav')}")
        return np.frombuffer(wav.readframes(wav.getnframes()), "<i2").astype(np.float32) / 32768


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS, KiB on Linux
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def wav_files(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_dir():
            found = sorted(path.glob("*.wav"))
            if not found:
                raise SystemExit(f"error: no .wav files in {path}")
            files += found
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"error: {path} not found")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="WAV files or folders of WAVs")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=1, help="runs per file; the median time is shown")
    args = parser.parse_args()
    if args.repeat < 1 or args.threads < 1:
        raise SystemExit("error: --repeat and --threads must be >= 1")
    clips = [(path, read_wav(path)) for path in wav_files(args.paths)]   # bad files fail before the slow load

    before = peak_rss_mb()
    started = time.perf_counter()
    from transcriber.asr import Transcriber   # imported here so its import time counts as load time
    transcriber = Transcriber(threads=args.threads)
    load_s = time.perf_counter() - started
    after = peak_rss_mb()
    print(f"{args.threads} thread(s): loaded in {load_s:.2f} s "
          f"(incl. imports and warm-up); peak RSS {after:.0f} MB (+{after - before:.0f} MB for ASR)")

    total_audio = total_time = 0.0
    for path, audio in clips:
        original = audio.copy()
        times = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            text = transcriber.transcribe(audio)
            times.append(time.perf_counter() - t0)
        if not np.array_equal(audio, original):
            raise SystemExit(f"error: transcribe() changed its input ({path})")
        seconds = len(audio) / SAMPLE_RATE
        took = statistics.median(times)
        total_audio += seconds
        total_time += took
        spread = f" (min {min(times):.3f}, max {max(times):.3f})" if args.repeat > 1 else ""
        print(f"\n{path}: {seconds:.2f} s audio, peak {np.abs(audio).max():.3f}, "
              f"{took:.3f} s{spread}, RTF {took / seconds:.3f}")
        print(f"  HY: {text if text else '(empty)'}")

    print(f"\n{len(clips)} file(s), {total_audio:.1f} s audio in {total_time:.2f} s: "
          f"RTF {total_time / total_audio:.3f}; peak RSS {peak_rss_mb():.0f} MB")


if __name__ == "__main__":
    main()
