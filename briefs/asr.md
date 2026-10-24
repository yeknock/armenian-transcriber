# Brief — asr

**Goal:** Armenian audio → Armenian text with `nvidia/stt_hy_fastconformer_hybrid_large_pc` (D1), and
settle D1a: Transducer decoder vs CTC decoder, and NeMo vs ONNX (`onnx-asr`).

**Read:** `MODULES.md`, `transcriber/contracts.py`, `transcriber/asr.py`, `DECISIONS.md` D0 and D1.

**May edit:** `transcriber/asr.py`, `scripts/try_asr.py`, `requirements.txt` (append),
`DECISIONS.md` (D1a), `TESTS.md` (asr section), this brief.

## Contract (signature in `transcriber/asr.py`)
- `Transcriber()` loads the model once and raises if it cannot.
- `transcribe(audio) -> str`: input is float32 mono 16 kHz, about 0.3–15 s, and is not modified.
  It returns Armenian text with punctuation. `""` only when the model outputs nothing.
- Called from one worker thread. No network after the first download.

## Verify first (sources, not memory)
- The model card: input format, which decoders it has, licence.
- How to switch a NeMo hybrid model between its Transducer (RNNT) and CTC decoders. If that works, both
  can be compared without a second library.
- Whether `onnx-asr` really supports this model.
- NeMo's install on macOS arm64 with Python 3.12: watch which numpy and torch versions it pulls in (rule 7).

## Approach
Get **one** path working first: the one that installs cleanly. Measure it. Try the second path only if
the install is cheap. Record the numbers either way.

## Standalone check
```
python -m scripts.try_asr eval/audio/test_mic.wav eval/audio/test_call.wav
```
At start it prints load time and RSS. For each file it prints the text, the audio length, the processing
time and the real-time factor.

## Done when
- [ ] Armenian text for ≥ 3 of our own recordings (mic + through BlackHole), checked by eye
- [ ] load time, RSS and time for a 10 s clip in Status (targets: ≤ 1.0 GB, ≤ 0.8 s)
- [ ] works with Wi-Fi off
- [ ] D1a decided with numbers, or deferred to the eval chat with the numbers so far

**Out of scope:** VAD, streaming ASR, translation.

## Status
(not started)

## Contract questions
(none)
