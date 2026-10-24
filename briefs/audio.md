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
- [ ] wrong name, ambiguous name and output-only device each give a clear error
- [ ] 60 s with both sources: chunk count within 1 % of expected, clock difference < 0.1 s, 0 dropouts
- [ ] a recorded WAV is 16 kHz mono and sounds right (correct speed, no clicks)

**Out of scope:** VAD, echo, devices plugged in or out while running.

## Status
(not started)

## Contract questions
(none)
