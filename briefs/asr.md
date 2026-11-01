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
- [x] Armenian text for ≥ 3 of our own recordings (mic + through BlackHole), checked by eye — 4 recordings (18
  segments) plus live Zoom calls; checked by the user
- [x] load time, RSS and time for a 10 s clip in Status (targets: ≤ 1.0 GB, ≤ 0.8 s) — 9.8 s, **+1.37 GB (over)**, 0.35 s
- [x] works with Wi-Fi off (TESTS ASR6, user 2026-11-01)
- [x] D1a decided with numbers — RNNT head with NeMo (D1a); competitors checked (D1b)

**Out of scope:** VAD, streaming ASR, translation.

## Status
**Done (2026-11-01), chat `05-asr`** (the same chat also started the mt module).
Commit: `102f7be Finished ASR module. NeMo with RNNT head.` (also holds the mt work so far). VAD tests pass after the NeMo install (TESTS ASR9).

**What exists:**
- `transcriber/asr.py`: `Transcriber(threads=4)` loads `models/nvidia_hy_nemo/*.nemo` with NeMo 3.0.0, RNNT head, CPU,
  eval mode; warm-up on 1 s of silence. `transcribe(audio)` checks the input (1-D float32, finite, 0.1–20 s), gives
  NeMo a copy (NeMo does not copy numpy arrays), returns the text stripped; a strange NeMo result raises.
- `scripts/try_asr.py`: WAV files or folders of WAVs (e.g. the VAD's cuts) → text, length, time, RTF per file; load
  time and peak memory; `--threads`, `--repeat`; stops if `transcribe()` changed its input.
- `scripts/live_asr.py` (not in the *May edit* list; added on the user's request to test with real calls before the
  full program exists): mic + BlackHole → VAD → ASR, prints time, `Me` / `Call`, Armenian and the delay split into
  VAD + queue + ASR; Ctrl+C still finishes the last phrase; warns when the mic is digital silence (macOS permission)
  or BlackHole is (call app not on "Call Output"); `--save` keeps every phrase as WAV + text in `logs/`.
- `requirements.txt`: `nemo_toolkit[asr]==3.0.0`. Model files in `models/` (git-ignored); download command in the
  error message. Everything else tried in this chat was removed (onnx-asr, three competitor models, the NeMo venv).

**Later (2026-11-01, after chat 06):** `Transcriber(threads=4, beam_size=1)`: beam_size > 1 = NeMo `malsd_batch` beam
search (sets `return_best_hypothesis` to true; the checkpoint stores false). Measured on `eval/real`: no gain, 2.3× the
time, so the default stays greedy (D1a, TESTS EV3).

**Measured on the M1:** see D1a, D1b and TESTS ASR1–ASR10, L1–L4. Live 10.8 min Zoom call (ASR only): 185 phrases,
p95 3.38 s, max 3.76 s, 0 over 5 s.

**Notes for other chats:**
- *integration:* `scripts/live_asr.py` is a working start for `pipeline.py` (threads, queue, Ctrl+C, flush, delay
  breakdown, routing checks): reuse or replace it. Load the ASR model **before** starting the audio (10 s; 68–97 s on
  the first start after an install). Mic-side phrases were handed over ~2 s late in a real call (D2 "Found in live
  calls"): measure again with translation in the loop (R7). Users must set the call app's speaker to "Call Output".
- *mt:* the ASR ends sentences with `։` (262 in our logs), sometimes `.`; `՞ ՜` are inside words; one segment can hold
  several sentences.
- *speakers:* NeMo and torch are in `.venv` now, so TitaNet (D4) adds no new library.

## Contract questions
1. **`torch.set_num_threads(threads)` is process-wide.** Every torch model in the program (speakers) shares the
   setting made by `Transcriber`. Integration: set it once on purpose, and log it in DECISIONS.
2. **Memory budget:** ASR uses +1.37 GB, not ≤ 1.0 GB (MODULES budgets). The whole-program target (~3.5 GB) still
   looks reachable with NLLB-600M (measured since: +1.07 GB, whole program ~2.7 GB estimate, D3a); to be measured
   as a whole in integration. The lighter onnx-asr path (+0.58 GB,
   same text) is documented in D1a if needed.
3. **`MAX_SECONDS = 20`** (the contract says ~0.3–15 s): the model was trained on 0.1–20 s; longer input raises.
4. **Model files live in the repo's git-ignored `models/`** (decided with the user), not in a cache outside the repo
   as MODULES rule 6 first said; rule 6 was updated (2026-11-01).
