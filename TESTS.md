# TESTS

Checks come from the brief's requirements (PLAN.md §1), not from the code (Tip 4).
Module chats add their own section at the bottom.
Result: ✅ pass · ❌ fail (+ note) · ⬜ not run

## Requirements (end to end)

| ID | Check | Result |
|---|---|---|
| R1 | Mic and BlackHole levels move independently (`scripts/level_meter.py`) | ✅ 2026-10-24 |
| R2a | `python main.py --list-devices` prints the input devices | ⬜ |
| R2b | `python main.py --mic "MacBook Air Microphone" --call BlackHole` starts | ⬜ |
| R2c | Wrong or ambiguous device name → clear error, non-zero exit code | ⬜ |
| R3 | CER/WER on the eval set reported | ⬜ |
| R4 | English of every eval clip rated good / ok / bad by an Armenian speaker | ⬜ |
| R5a | Mic lines are always `Me` | ⬜ |
| R5b | Scripted call, 2 call-side people taking ≥ 10 turns → each keeps one label (accuracy %) | ⬜ |
| R5c | A 3rd call-side person gets a new label | ⬜ |
| R6 | Every printed entry has time, speaker, HY and EN | ⬜ |
| R7a | 10-min call: latency p50 / p95 / max from `logs/latency.csv`; p95 ≤ 5 s | ⬜ |
| R7b | Both sides talking at once: p95 still ≤ 5 s | ⬜ |
| R8 | Whole run works with Wi-Fi off | ⬜ |

## Edge cases

| ID | Check | Result |
|---|---|---|
| E1 | 1 min of silence / room noise → nothing printed | ⬜ |
| E2 | 30 s non-stop speech → split into several entries, each ≤ 5 s late | ⬜ |
| E3 | Very short reply ("Այո") → printed; does not create a new speaker | ⬜ |
| E4 | Ctrl+C → exits within ~1 s, no traceback | ⬜ |
| E5 | Microphone permission missing → clear message naming the setting | ⬜ |
| E6 | Call audio on speakers → how often echo shows up as `Me` (measure; echo handling is out of scope) | ⬜ |

## Module checks

(Each module chat adds its section here: audio, vad, asr, mt, speakers, eval.)

### audio (chat 03, MacBook Air M1)

"Test env" = run by Claude without real devices (generated audio / fake sound card); the rest ran on the Mac.

| ID | Check | Result |
|---|---|---|
| A1 | `python -m scripts.try_audio --list` shows only input devices (BlackHole 2ch, MacBook Air Microphone) | ✅ 2026-10-30 |
| A2 | Wrong name (`zoom`), ambiguous (`"MacBook Air"`), output-only (`"Call Output"`) → clear error, exit ≠ 0 | ✅ 2026-10-30 |
| A3 | `--selftest`: 48 / 44.1 kHz, mono / stereo, random block sizes → exact 512-sample chunks, exact start times, matches an ideal 16 kHz tone (error < 1e-3), block size has no effect, values in [-1, 1] | ✅ 2026-10-30 (Mac + test env) |
| A4 | The self-test fails if each block is resampled on its own (bug planted on purpose) | ✅ test env |
| A5 | 60 s, both sources, YouTube + two people talking: chunks within 1 %, lag < 0.1 s, 0 dropouts | ✅ 2026-10-30: 0.01 % / 0.02 %, max 59 / 46 ms, 0 |
| A6 | Callback crash or worker error → `RuntimeError` naming the source; driver overflow counted as a dropout | ✅ test env |
| A7 | Ctrl+C during `try_audio` → "Stopped early.", result printed, no traceback | ✅ 2026-10-30 |
| A8 | `record.py` writes 16 kHz mono 16-bit, exact length, correct pitch, no clicks (440 Hz tone read back); refuses an existing file and `--seconds 0`; Ctrl+C writes nothing, no traceback | ✅ test env |
| A9 | `record.py` clips from mic and BlackHole sound right | ✅ 2026-10-31 (the mic clip also has the speaker sound: echo, see E6) |
| A10 | `dropouts` stay 0 with ASR + MT running (`latency="low"` means a mic callback every 1.3 ms) | ⬜ M5 soak test |

### vad (chat 04, MacBook Air M1)

"Test env" = run by Claude on Linux with the same recordings; "Mac" = run by the user. Both gave identical cuts.

| ID | Check | Result |
|---|---|---|
| V1 | `_SileroModel` (our onnxruntime code) gives the same probabilities as Silero's official wrapper, on every WAV in `eval/audio/` and on generated audio (≤ 1e-6; actual 0.0) | ✅ 2026-10-31 Mac + test env |
| V2 | Using the VAD never imports torch (fresh process) | ✅ 2026-10-31 Mac + test env |
| V3 | Segmenter rules with a fake model (`tests/test_vad.py`, 24 tests): pre-roll, padding, end time, hysteresis, short pause kept, drops counted, early cut after 5 s in the middle of a 96 ms dip, quiet hard cut at 10 s, no overlap / no lost audio, wrong source and gaps raise | ✅ 2026-11-01 Mac + test env |
| V4 | 15 planted bugs (no pre-roll, wrong end, unsure = speech, no early cut, cut at the loudest point, …) each make at least one test fail | ✅ 2026-11-01 test env |
| V5 | 60 s room noise → 0 segments, 0 dropped | ✅ 2026-11-01 Mac |
| V6 | 5 phrases with ~3 s pauses → 5 segments; a phrase with 100–150 ms pauses inside stays one segment | ✅ 2026-11-01 Mac, listened: each phrase whole |
| V7 | Short replies (Այո, Ոչ, Հա, Լավ, Մերսի) → all 5 kept, none dropped (VAD part of E3) | ✅ 2026-11-01 Mac |
| V8 | 35 s nonstop speech → pieces ≤ 10 s (longest 9.60 s) | ✅ 2026-11-01 |
| V9 | VAD's share of latency: 0.32–0.35 s after a phrase, 0.06 s after an early cut, 0.13–0.61 s after a quiet hard cut | ✅ 2026-11-01 |
| V10 | Time per `feed()`: median 0.10 ms, max 0.41 ms on the M1 (target: a few ms) | ✅ 2026-11-01 Mac |
| V11 | Listening: every segment of `test_mic` and `call_speech` incl. both early cuts — no word, first syllable or ending cut | ✅ 2026-10-31 user |
| V12 | Listening: the 4 quiet hard cuts (`nonstop` 24.000 s, `call_interview` 9.792 / 25.280 / 34.656 s) fall between words; all segments of all 7 recordings sound right (short replies cut to just the word) | ✅ 2026-11-01 user |
| V13 | Memory: both Segmenters ~53 MB, whole `try_vad` process 78–83 MB peak, torch not loaded (budget: ≤ 50 MB per Segmenter) | ✅ 2026-11-01 test env (Mac peak not recorded) |
| V14 | No network: with networking switched off, all 24 tests pass and `try_vad` cuts as usual (MODULES rule 6) | ✅ 2026-11-01 test env |
