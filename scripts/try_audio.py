"""Standalone checks for the audio module (briefs/audio.md).

Run from the repo root:
    python -m scripts.try_audio --list
    python -m scripts.try_audio --selftest
    python -m scripts.try_audio --mic "MacBook Air Microphone" --call BlackHole --seconds 60
"""
import argparse
import queue
import time

import numpy as np
import sounddevice as sd

from transcriber.audio import AudioCapture, _Rechunker, list_input_devices, resolve_device
from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_CALL, SOURCE_MIC

CHUNK_SECONDS = CHUNK_SAMPLES / SAMPLE_RATE
PROGRESS_EVERY_S = 5
MAX_COUNT_ERROR = 0.01   # brief: chunk count within 1 % of expected
MAX_LAG_S = 0.1          # brief: clock difference < 0.1 s

SELFTEST_SECONDS = 10
TONE_HZ = 1000


def describe(label: str, spec: str) -> int:
    device_id = resolve_device(spec)
    info = sd.query_devices(device_id)
    print(f"{label}: {spec!r} -> id {device_id} {info['name']!r}, "
          f"{info['max_input_channels']} input ch, {info['default_samplerate']:.0f} Hz")
    return device_id


def live(mic_id: int, call_id: int, seconds: float) -> None:
    """Capture both devices at once and check chunk count, clock lag, dropouts and peak."""
    out: queue.Queue = queue.Queue()
    session_start = time.monotonic()
    captures = {SOURCE_MIC: AudioCapture(SOURCE_MIC, mic_id, session_start, out),
                SOURCE_CALL: AudioCapture(SOURCE_CALL, call_id, session_start, out)}
    counts = {source: 0 for source in captures}
    first_arrival = {source: float("nan") for source in captures}   # session seconds
    last_arrival = {source: float("nan") for source in captures}
    last_lag = {source: float("nan") for source in captures}
    max_lag = {source: 0.0 for source in captures}
    interval_max_lag = {source: 0.0 for source in captures}   # reset at every progress line

    def take(chunk) -> None:
        now = time.monotonic() - session_start
        # lag = how long after the chunk's last sample it reached us (device buffer + resampler + queues)
        lag = now - (chunk.start + CHUNK_SECONDS)
        if counts[chunk.source] == 0:
            first_arrival[chunk.source] = now
        last_arrival[chunk.source] = now
        counts[chunk.source] += 1
        last_lag[chunk.source] = lag
        max_lag[chunk.source] = max(max_lag[chunk.source], lag)
        interval_max_lag[chunk.source] = max(interval_max_lag[chunk.source], lag)

    print(f"Capturing for {seconds:g} s. Speak, and play something to 'Call Output'. Ctrl+C stops early.")
    next_progress = PROGRESS_EVERY_S
    try:
        for capture in captures.values():
            capture.start()
        while (elapsed := time.monotonic() - session_start) < seconds:
            try:
                take(out.get(timeout=0.2))   # wake up regularly to call check()
            except queue.Empty:
                pass
            for capture in captures.values():
                capture.check()
            if elapsed >= next_progress:
                next_progress += PROGRESS_EVERY_S
                print(f"  {elapsed:5.1f} s   " + "   ".join(
                    f"{s}: {counts[s]} chunks, lag max {interval_max_lag[s] * 1000:3.0f} ms, "
                    f"peak {captures[s].peak:.3f}, dropouts {captures[s].dropouts}" for s in captures))
                for source in interval_max_lag:
                    interval_max_lag[source] = 0.0
    except KeyboardInterrupt:
        print("\nStopped early.")
    finally:   # always release the devices and threads, also when check() raised
        stop_begin = time.monotonic()
        for capture in captures.values():
            capture.stop()
        stop_seconds = time.monotonic() - stop_begin
    for capture in captures.values():
        capture.check()   # errors from the last moments before stop()

    # Only chunks taken while capturing are measured. Chunks still queued now waited during
    # stop() (which can take ~0.1-0.3 s on macOS); measuring them would add that wait to the lag.
    # Expected chunks are counted over the time chunks were arriving (first to last arrival).
    print(f"\nResult (measured while capturing; stopping took {stop_seconds * 1000:.0f} ms, "
          f"{out.qsize()} chunks still queued were not measured):")
    all_ok = True
    for source, capture in captures.items():
        if counts[source] < 2:
            raise SystemExit(f"{source}: only {counts[source]} chunks arrived; nothing to measure.")
        span = last_arrival[source] - first_arrival[source]
        expected = span / CHUNK_SECONDS + 1
        count_error = abs(counts[source] - expected) / expected
        print(f"  {source}: first chunk after {first_arrival[source]:.2f} s, "
              f"chunks arrived for {span:.1f} s")
        checks = {
            f"chunks {counts[source]} vs expected {expected:.0f} ({count_error:.2%} off)":
                count_error <= MAX_COUNT_ERROR,
            f"clock lag last {last_lag[source] * 1000:.0f} ms, max {max_lag[source] * 1000:.0f} ms":
                max_lag[source] < MAX_LAG_S,
            f"dropouts {capture.dropouts}": capture.dropouts == 0,
            f"peak {capture.peak:.3f}": capture.peak > 0.0,
        }
        for text, ok in checks.items():
            print(f"    {'PASS' if ok else 'FAIL'}  {text}")
            all_ok &= ok
        if capture.peak == 0.0:
            print("    peak 0.0 = only digital silence. Check System Settings -> Privacy & Security -> "
                  "Microphone (allow your terminal app), and that sound is playing to 'Call Output'.")
    print("LIVE CHECK PASSED" if all_ok else "LIVE CHECK FAILED")
    if not all_ok:
        raise SystemExit(1)


def _push_all(rechunker: _Rechunker, signal: np.ndarray, block_sizes) -> list:
    chunks, i = [], 0
    for size in block_sizes:
        if i >= len(signal):
            break
        chunks += rechunker.push(signal[i:i + size])
        i += size
    return chunks


def selftest() -> None:
    """Offline checks of resampling + chunking with generated audio (no devices needed)."""
    failures = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
        if not ok:
            failures.append(name)

    rng = np.random.default_rng(0)
    t0 = 1.25
    for rate in (48_000, 44_100):
        for channels in (1, 2):
            print(f"{rate} Hz, {channels} ch, {SELFTEST_SECONDS} s, random block sizes 1..2048:")
            t = np.arange(rate * SELFTEST_SECONDS) / rate
            tone = 0.5 * np.sin(2 * np.pi * TONE_HZ * t)
            if channels == 1:
                signal = tone[:, None]
            else:   # left and right differ, but their average is exactly the tone
                other = 0.3 * np.sin(2 * np.pi * 440 * t)
                signal = np.stack([tone + other, tone - other], axis=1)
            signal = signal.astype(np.float32)

            random_blocks = rng.integers(1, 2049, size=len(signal))
            chunks = _push_all(_Rechunker("mic", rate, channels, t0), signal, random_blocks)

            shapes_ok = all(c.samples.shape == (CHUNK_SAMPLES,) and c.samples.dtype == np.float32
                            and c.source == "mic" for c in chunks)
            check("chunk format", shapes_ok, f"{len(chunks)} chunks of {CHUNK_SAMPLES} float32, source 'mic'")

            expected_starts = t0 + np.arange(len(chunks)) * CHUNK_SAMPLES / SAMPLE_RATE
            start_err = float(np.max(np.abs(np.array([c.start for c in chunks]) - expected_starts)))
            check("start times", start_err < 1e-9, f"max error {start_err:.1e} s vs t0 + i*0.032")

            ideal_count = SELFTEST_SECONDS * SAMPLE_RATE / CHUNK_SAMPLES
            count_ok = ideal_count - 3 <= len(chunks) <= ideal_count
            check("chunk count", count_ok, f"{len(chunks)} (ideal {ideal_count:g}; the resampler holds back a few ms)")

            out = np.concatenate([c.samples for c in chunks])
            ideal = 0.5 * np.sin(2 * np.pi * TONE_HZ * np.arange(len(out)) / SAMPLE_RATE)
            tone_err = float(np.max(np.abs(out[100:] - ideal[100:])))
            check("speed, timing, no clicks, mono mix", tone_err < 1e-3,
                  f"max difference from an ideal 16 kHz {TONE_HZ} Hz tone = {tone_err:.1e}")

            fixed_blocks = [480] * len(signal)
            out_fixed = np.concatenate([c.samples for c in
                                        _push_all(_Rechunker("mic", rate, channels, t0), signal, fixed_blocks)])
            n = min(len(out), len(out_fixed))
            same = float(np.max(np.abs(out[:n] - out_fixed[:n])))
            check("block size has no effect", same < 1e-6, f"random vs 480-frame blocks differ by {same:.1e}")

    print("Edge cases:")
    square = np.sign(np.sin(2 * np.pi * 200 * np.arange(48_000) / 48_000)).astype(np.float32)[:, None]
    peak = max(float(np.max(np.abs(c.samples))) for c in
               _push_all(_Rechunker("call", 48_000, 1, 0.0), square, [1024] * len(square)))
    check("values stay in [-1, 1]", peak <= 1.0, f"full-scale square wave -> peak {peak:.3f}")

    try:
        _Rechunker("call", 48_000, 2, 0.0).push(np.zeros((480, 1), dtype=np.float32))
        check("wrong block shape is rejected", False, "no error raised")
    except ValueError as error:
        check("wrong block shape is rejected", True, f"ValueError: {error}")

    if failures:
        raise SystemExit(f"SELFTEST FAILED: {', '.join(failures)}")
    print("SELFTEST PASSED")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the input devices and exit")
    parser.add_argument("--selftest", action="store_true",
                        help="check resampling and chunking with generated audio (no devices)")
    parser.add_argument("--mic", help="microphone: device id or part of its name")
    parser.add_argument("--call", help="call audio (BlackHole): device id or part of its name")
    parser.add_argument("--seconds", type=float, default=60, help="how long to capture (default 60)")
    args = parser.parse_args()

    if args.list:
        print(list_input_devices())
        return
    if args.selftest:
        selftest()
        return
    if args.mic is None or args.call is None:
        parser.error("give --list, --selftest, or both --mic and --call")
    try:
        mic_id = describe("mic ", args.mic)
        call_id = describe("call", args.call)
    except ValueError as error:
        raise SystemExit(f"error: {error}")
    live(mic_id, call_id, args.seconds)


if __name__ == "__main__":
    main()
