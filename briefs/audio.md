# Brief — audio

**Goal:** list and pick input devices, and capture the mic and BlackHole at the same time as
16 kHz mono `AudioChunk`s on one shared session clock (requirements R1, R2).

**Read:** `MODULES.md`, `transcriber/contracts.py`, `transcriber/audio.py`,
`scripts/level_meter.py` (working M0 code to build on), `DECISIONS.md` D0.

**May edit:** `transcriber/audio.py`, `scripts/try_audio.py`, `scripts/record.py`,
`requirements.txt` (append), `TESTS.md` (audio section), this brief (Status, Contract questions).

## Contract (signatures in `transcriber/audio.py`)
- `list_input_devices() -> str`; `resolve_device(spec) -> int` takes an id **or** part of a name.
  Names are the normal way, because device numbers change when devices are plugged in.
  It raises `ValueError` when nothing matches, more than one device matches, or the device has no input.
- `AudioCapture(source, device, session_start, out)` with `.start()`, `.stop()`, `.dropouts`, `.peak`.
- Every chunk has exactly `CHUNK_SAMPLES` float32 samples, mono, 16 kHz. Stereo becomes mono by averaging the channels.
  The device's own rate (often 48 kHz or 44.1 kHz) is resampled to 16 kHz.
- `chunk.start` is counted from the number of samples received since the first callback, so it does not
  drift. Both sources use the same `session_start`.
- The audio callback only copies data. Resampling and chunking run outside it. This is the only module
  allowed to start its own thread.

## To decide (and verify in the docs)
- Resampler: it must resample a *stream* without clicks at chunk borders. One candidate is python-soxr's
  streaming resampler. Check its API before using it. Do not resample each chunk on its own.

## Standalone checks
```
python -m scripts.try_audio --list
python -m scripts.try_audio --mic "MacBook Air Microphone" --call BlackHole --seconds 60
python -m scripts.record --device BlackHole --seconds 10 --out eval/audio/test_call.wav
```
`try_audio` prints for each source: chunks received vs expected (`seconds × 16000 / 512`), the difference
between the last `chunk.start` and the wall clock, dropouts, and peak.

## Done when
- [x] wrong name, ambiguous name and output-only device each give a clear error
- [x] 60 s with both sources: chunk count within 1 % of expected, clock difference < 0.1 s, 0 dropouts
- [x] a recorded WAV is 16 kHz mono and sounds right (correct speed, no clicks)

**Out of scope:** VAD, echo, devices plugged in or out while running.

## Status
**Done (2026-10-31), chat `03-audio`.** Commits: `audio: list and resolve input devices`,
`audio: streaming resample and chunking`, `audio: AudioCapture with low-latency streams and live two-device check`,
`audio: record.py for 16 kHz mono test clips`.

**What exists** (`transcriber/audio.py`):
- `list_input_devices()`, `resolve_device(spec)` — exact full name wins over part-of-name matches; errors list the candidates.
- `_Rechunker` (internal, no threads/devices): mono mix → `soxr.ResampleStream` → exact 512-sample chunks,
  `start = t0 + emitted / 16000`; output clipped to [-1, 1].
- `AudioCapture`: callback copies blocks → worker thread runs `_Rechunker` → `out`. Device's own rate, ≤ 2 channels,
  `latency="low"`. Extra method `check()` (see Contract questions). `stop()` only cleans up and never raises.

**Measured on the MacBook Air M1** (60 s, YouTube on Call Output + two people talking): chunk count 0.01 % / 0.02 % off,
lag (chunk end → in our hands) max 59 ms mic / 46 ms call, 0 dropouts. Streams need ~0.25 s to deliver the first chunk;
stopping both takes ~0.25 s. Device blocks with `latency="low"`: mic 64 frames, BlackHole 480 frames (with the default
`"high"`: 512 and 4096 = 85 ms).

**Notes for the integration chat:**
- Call `check()` on both captures in the main loop (e.g. every 0.2 s) and once after `stop()`; wrap the loop in
  `try/finally` that calls `stop()` on both (see `scripts/try_audio.py live()`).
- Measure latency only on chunks taken while capturing; chunks left in the queue during `stop()` wait ~0.25 s.
- The mic also hears the call through the speakers (echo, out of scope; TESTS E6).
- With `latency="low"` the mic callback runs every 1.3 ms: watch `dropouts` under full ASR+MT load (TESTS A10).

## Contract questions
1. **`AudioCapture.check()` was added** (not in the original interface). Errors on the audio callback thread and the
   worker thread do not reach the main thread by themselves (sounddevice docs: exceptions in the callback are
   "not propagated to the main thread", and the callback is not called again). `check()` raises `RuntimeError`
   if the worker failed or the stream stopped by itself. Integration chat: confirm and log in DECISIONS.md.
