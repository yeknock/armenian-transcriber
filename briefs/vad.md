# Brief — vad

**Goal:** cut one source's chunk stream into whole-phrase `Segment`s with Silero VAD (D2).

**Read:** `MODULES.md`, `transcriber/contracts.py`, `transcriber/vad.py`, `DECISIONS.md` D2 and D5.

**May edit:** `transcriber/vad.py`, `scripts/try_vad.py`, `tests/test_vad.py`, `requirements.txt` (append),
`TESTS.md` (vad section), this brief.

## Contract (signatures in `transcriber/vad.py`)
- `Segmenter(source, **tuning)`, `.feed(chunk) -> list[Segment]`, `.flush() -> list[Segment]`, `.dropped_short`.
- Push-based: no threads, no queues, no clock reads. All times come from `chunk.start`, so a WAV file
  gives the same result as live audio.
- `Segment.end` is the end of the speech plus padding, **not** the moment the silence was confirmed.
- `Segment.audio` includes a little audio before the speech starts, so the first syllable is not cut.
- Long speech is cut at a maximum length, at a short pause if there is one. Each piece is its own `Segment`.
- Bursts shorter than the minimum length are dropped and counted in `dropped_short`, so the drops stay visible.
- One `Segmenter` per source, because Silero keeps state per stream.

## To decide by measuring
Defaults for: threshold, min silence (PLAN: ~400–800 ms), speech padding, max segment (~10–15 s),
min segment. Verify the silero-vad API (512 samples at 16 kHz, how to reset state) in its docs.

## Standalone check
```
python -m scripts.try_vad eval/audio/test_mic.wav
```
This feeds the WAV in 512-sample chunks, prints each segment's start, end and length, and writes each one
to `eval/audio/segments/` so you can listen to it. Make test WAVs with `scripts/record.py` (audio module),
or convert any recording with `ffmpeg -i input.m4a -ar 16000 -ac 1 eval/audio/test_mic.wav`.

## Done when
- [x] 1 min of room noise → 0 segments (`room_noise.wav`: 0 segments, 0 dropped)
- [x] 5 phrases with pauses → 5 segments, none cut mid-word (listened to) — 5 segments, each phrase whole; all
  segments of all 7 recordings listened to (user, 2026-11-01)
- [x] 30 s non-stop speech → pieces no longer than the max length (`nonstop.wav`: longest 9.60 s)
- [x] time per `feed()` call measured (M1: median 0.10 ms, max 0.41 ms)
- [x] chosen defaults with their reasons written into D2 (Tentative → Decided)

**Out of scope:** speaker labels, ASR, echo.

## Status
**Done (2026-11-01), chat `04-vad`.** Commits: `vad: Silero ONNX model wrapper and tests`,
`vad: Segmenter with pre-roll, padding, hysteresis and early cut for long speech`,
`vad: try_vad.py standalone check on WAV files`, `vad: quiet hard cut, tuning, D2, tests and status`.
`DECISIONS.md` (D2) was edited with the user's permission (it is in the done-list but was missing from *May edit*).

**What exists** (`transcriber/vad.py`):
- `_SileroModel`: runs the `.onnx` file from the installed `silero-vad==6.2.3` package with onnxruntime (1 thread);
  keeps the 64-sample context and the model's memory; `reset()`. Never imports `silero_vad` or torch (D2).
- `Segmenter(source, *, threshold=0.5, neg_threshold=0.35, min_silence_ms=500, pad_ms=200, soft_max_s=5.0,
  min_dip_ms=96, max_segment_s=10.0, quiet_search_ms=1000, min_speech_ms=250)`: `feed()`, `flush()`, `dropped_short`.
  Rules and the measured reasons for every value: D2. Bad settings raise `ValueError`.
- `scripts/try_vad.py`: WAVs → table of segments (with how long after its end each was handed over), `feed()` time,
  peak memory, one WAV per segment in `eval/audio/segments/<name>/`, `--timeline` (score + segment per chunk), every
  setting as a flag (e.g. `--min-silence-ms 600`).
- `tests/test_vad.py`: 24 tests (`python -m unittest tests.test_vad -v`); checks in TESTS.md V1–V14.

**Measured** (7 recordings, M1): VAD's share of latency 0.32–0.35 s after a phrase, 0.06 s after an early cut,
≤ 1 s (measured 0.13–0.61 s) after a quiet hard cut; 0.10 ms per chunk; ~53 MB for both Segmenters (Linux).

**Notes for other chats:**
- *integration:* one `Segmenter` per source; feed chunks in order (a gap raises). Call `flush()` at shutdown.
  `Segment.start` includes the 192 ms pre-roll, so the printed time is ~0.2 s before the first word.
  **Never `import silero_vad`** anywhere in the program: it switches torch to one thread for the whole process.
  MODULES.md latency line says "silence needed to close it (~0.6 s)": measured 0.32 s (early cut 0.06 s, hard cut ≤ 1 s).
- *asr:* segments are 0.6–10 s (≤ 9.98 s), start with ~192 ms of non-speech; call-side audio is quiet (peak 0.09–0.14).
- *speakers:* two call-side people speaking back to back with no gap can end up in one segment (one label).
  Segments of long speech are cut into pieces of ~5–10 s, each labelled on its own.

## Contract questions
1. **New tuning arguments:** `soft_max_s`, `min_dip_ms`, `quiet_search_ms` (besides those the brief named), all with
   defaults, so `Segmenter(source)` still works. Integration chat: nothing to change.
2. **`Segment.start` / `end` = first / last sample of `Segment.audio`** (pre-roll and padding included), so
   `end − start == len(audio) / 16000` exactly. `end` is still the end of the speech plus padding, as the contract says.
