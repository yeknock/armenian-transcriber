"""Record one input device to a 16 kHz mono 16-bit WAV, through the same AudioCapture the program uses.

For test clips (eval/audio/ is git-ignored; never commit audio). Run from the repo root:
    python -m scripts.record --device BlackHole --seconds 10 --out eval/audio/test_call.wav
"""
import argparse
import queue
import time
import wave
from pathlib import Path

import numpy as np

from transcriber.audio import AudioCapture, resolve_device
from transcriber.contracts import SAMPLE_RATE, SOURCE_MIC


def record(device_id: int, seconds: float) -> tuple[np.ndarray, float]:
    """Return exactly `seconds` of 16 kHz mono float32 audio and its peak."""
    out: queue.Queue = queue.Queue()
    # The source label is not stored in the WAV; any valid label works here.
    capture = AudioCapture(SOURCE_MIC, device_id, time.monotonic(), out)
    needed = int(round(seconds * SAMPLE_RATE))
    chunks, have = [], 0
    try:
        capture.start()
        while have < needed:
            try:
                chunk = out.get(timeout=0.2)   # wake up regularly to call check()
                chunks.append(chunk.samples)
                have += len(chunk.samples)
            except queue.Empty:
                pass
            capture.check()
    finally:
        capture.stop()
    capture.check()
    return np.concatenate(chunks)[:needed], capture.peak


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = np.round(np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)          # 16-bit
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", required=True, help="device id or part of its name")
    parser.add_argument("--seconds", type=float, required=True, help="length of the recording")
    parser.add_argument("--out", type=Path, required=True, help="WAV file to write (must not exist)")
    args = parser.parse_args()

    if args.seconds <= 0:
        parser.error("--seconds must be greater than 0")
    if args.out.exists():
        raise SystemExit(f"error: {args.out} already exists; choose another name or delete it first.")
    try:
        device_id = resolve_device(args.device)
    except ValueError as error:
        raise SystemExit(f"error: {error}")

    print(f"Recording {args.seconds:g} s from device {device_id}. Ctrl+C cancels (nothing is written).")
    try:
        audio, peak = record(device_id, args.seconds)
    except KeyboardInterrupt:
        raise SystemExit("\nCancelled; nothing was written.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_wav(args.out, audio)
    print(f"Wrote {args.out}: {len(audio) / SAMPLE_RATE:.2f} s, {SAMPLE_RATE} Hz, mono, 16-bit, peak {peak:.3f}")
    if peak == 0.0:
        print("Warning: peak 0.0 = only digital silence (Microphone permission, or nothing playing "
              "to 'Call Output').")


if __name__ == "__main__":
    main()
