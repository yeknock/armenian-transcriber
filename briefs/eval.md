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
- [ ] ≥ 10 clips with references
- [ ] metric unit tests pass
- [ ] baseline ASR table written into D1a (plus the other decoder or runtime if the asr chat has it)

**Out of scope:** MT scoring (the mt chat rates its own lines), speaker accuracy (the speakers chat).

## Status
(not started)

## Contract questions
(none)
