# Brief — integration

**Goal:** wire the finished modules into the program. v1 is the walking skeleton: mic only (M1), then both
sources (M2). v2 adds reliability (M5) and the README and rehearsal (M6).

**Read:** `MODULES.md`, `transcriber/contracts.py`, the module files (signatures and docstrings),
the *Status* and *Contract questions* sections of every brief, `PLAN.md` §3, `DECISIONS.md` D5, and
`scripts/live_asr.py`: it already runs mic + BlackHole → VAD → ASR → MT live (threads, queue, Ctrl+C, flush,
non-speech skip, latency breakdown, routing warnings), so it is the working start for `pipeline.py` (briefs/asr.md,
briefs/mt.md).

**Owns:** `transcriber/contracts.py` (changes are logged in DECISIONS), `transcriber/pipeline.py`,
`transcriber/output.py`, `main.py`, `README.md`, `.gitignore` (`logs/`), `TESTS.md` (requirements and edge cases).

## Design (PLAN §3, D5)
Two `AudioCapture`s feed one thread per source. Each thread runs `Segmenter.feed`, then labels the segment:
`"Me"` for the mic, `SpeakerIdentifier.identify` for the call side. Segments go into one queue, read by one
worker: `transcribe`, then `translate`. The main thread prints. Models load once at start-up.
- An exception in any thread stops the whole program and shows its traceback. No thread may die silently.
- Ctrl+C stops everything cleanly.
- Start-up: devices are resolved by name. If the mic gives only exact zeros for 3 s, show an error naming the
  macOS Microphone setting. Silence on the call side is normal.
- Every printed segment adds a row to `logs/latency.csv` (format in MODULES.md). At exit, print p50, p95 and max.

## CLI
```
python main.py --list-devices
python main.py --mic "MacBook Air Microphone" --call BlackHole
```

## Output (time = segment start on the session clock)
```
[00:01:12] Speaker 1
HY: Բարև, ինչպե՞ս ես։
EN: Hi, how are you?
```

## Done when
- v1: [ ] M1 (Armenian spoken into the mic shows HY and EN lines) · [ ] M2 (both sources in parallel)
- v2: [ ] 10-min soak test, p95 ≤ 5 s · [ ] R1–R8 and E1–E6 in TESTS.md run · [ ] README complete ·
  [ ] rehearsal call with ≥ 2 people on the call side

**Out of scope:** everything the brief lists as out of scope (GUI, saving transcripts, echo handling, …).

## Status
**v1 built (2026-11-01), not yet run on the Mac.** `main.py` (`--list-devices`, `--mic`, `--call`),
`transcriber/pipeline.py` (two captures → two Segmenters fed by the main thread → one worker: ASR, non-speech
dropped, speaker (call side), MT, print; `logs/latency.csv` with `speaker_s` added to the MODULES format; summary at
exit), `transcriber/output.py` (the brief's entry layout, indented HY / EN). Built from `scripts/live_asr.py`, which
stays as the diagnostic tool (latency breakdown per phrase). Speakers run in the worker after ASR, not in a thread
per source (simpler; coughs get no fingerprint). Checked in the test env with fake devices / models: entries, Ctrl+C
finishing the last phrases, summary, CSV, worker crash → traceback and exit 1, silent mic, wrong / same devices.
Next: README; live call on the Mac; 10-min soak test (R7a, A10).

## Contract questions
(none)
