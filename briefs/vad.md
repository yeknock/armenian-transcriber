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
- [ ] 1 min of room noise → 0 segments
- [ ] 5 phrases with pauses → 5 segments, none cut mid-word (listened to)
- [ ] 30 s non-stop speech → pieces no longer than the max length
- [ ] time per `feed()` call measured
- [ ] chosen defaults with their reasons written into D2 (Tentative → Decided)

**Out of scope:** speaker labels, ASR, echo.

## Status
(not started)

## Contract questions
(none)
