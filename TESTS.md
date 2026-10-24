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
