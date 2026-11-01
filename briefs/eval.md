# Brief — eval

**Goal:** a small evaluation set and scripts that turn "seems good" into numbers (Tip 5):
CER/WER for ASR and latency p50/p95/max. D1a and D3a were already decided on our recordings, by the user's
judgement and ratings (chats 05, 06); these numbers check those decisions and go into the README.

**Read:** `MODULES.md` (Shared formats), `transcriber/asr.py`, `PLAN.md` §7, `DECISIONS.md` D1.

**May edit:** `eval/` (scripts, `refs/`), `tests/test_metrics.py`, `requirements.txt` (append),
`DECISIONS.md` (D1a numbers), `TESTS.md` (R3, eval section), this brief.

## Eval set
- 10–20 clips of 3–10 s each in `eval/audio/` (git-ignored), recorded with `scripts/record.py`, some from the
  mic and some through BlackHole. Use different voices if possible, and include numbers, names and questions.
- Hand-typed reference text for each clip in `eval/refs/<same name>.txt` (committed).

## Scripts
- `eval/metrics.py`: `normalize(text)`, `cer(ref, hyp)`, `wer(ref, hyp)` (jiwer). The normalisation is written
  in the docstring: lowercase; remove Armenian punctuation (`։ ՝ ՞ ՜ ՛ ՚ « »`) and ASCII punctuation, with
  `:` used as a full stop; treat `և` and `եւ` as the same; collapse whitespace.
  Unit tests in `tests/test_metrics.py`.
- `eval/run_asr.py`: runs `Transcriber` over all clips and prints, per clip and in total, CER, WER and time.
- `eval/latency.py`: reads `logs/latency.csv` and prints p50, p95 and max, for each source and overall.

## Done when
- [ ] ≥ 10 clips with references — 3 so far (`eval/real/`, 121 s, 191 words; long clips, so more words than 10 short ones)
- [x] metric unit tests pass (TESTS EV1)
- [x] baseline ASR table written into D1a (plus the other decoder or runtime if the asr chat has it) — baseline, beam 4
  (D1a) and longer VAD phrases (D2), TESTS EV2–EV4

**Out of scope:** MT scoring (the mt chat rates its own lines), speaker accuracy (the speakers chat).

## Status
**In progress (2026-11-01), started in the docs-review / ASR-improvement chat after 06.**
- `eval/metrics.py`: `normalize`, `cer`, `wer` (jiwer 4.0.0, corpus level), `word_alignment`; the normalisation is in
  its docstring (as above, plus: every other mark becomes a space, so «տեսախցիկ։Ու» stays two words; digits kept).
  `tests/test_metrics.py`: 15 tests.
- `eval/run_asr.py`: WAVs + `--refs <folder>`; each clip goes VAD → ASR as in a live call (non-speech dropped as
  live), phrases joined, CER / WER per clip and in total, `--align` for word-by-word errors; `--beam`, `--soft-max-s`,
  `--max-segment-s` to try settings; report in `logs/eval_asr_<time>.txt`.
- Eval set: the user's `eval/real/` (MP3 + reference text) instead of `eval/audio/` + `eval/refs/`; WAVs converted with
  ffmpeg into `eval/audio/real/` (git-ignored).
- Results: TESTS EV2–EV4, D1a (beam rejected), D2 (longer phrases rejected).
- Not yet: `eval/latency.py` (the live script's CSV and summary already give p50 / p95 / max); call-side (BlackHole)
  clips and other voices; references corrected to exactly what was said (TESTS EV2).

## Contract questions
(none)
