# Handover 01 — end of session 1 (2026-10-24)

> Short handover for the next chat (Tip 6: goal, current state, decisions, next step).
> This is **not** the chat export. The full, unedited transcript of session 1 must be
> exported separately into `chats/` as its own `.md` file (brief requirement).

## Goal
Python terminal program: live call → Armenian transcription → English translation,
labelled by speaker (`Me` for mic, `Speaker 1/2/…` for call side, stable per session),
≤ 5 s from end of phrase to English line. Everything local (no cloud APIs).
Deliverables: Git repo with code, README (setup incl. audio, models + alternatives + why,
architecture, limitations), and all AI chats exported unedited to `chats/` (one `.md` per session).
~20 h of work, one week from brief (Oct 21, 2026). Interview: live call with ≥ 2 people on
the call side, on this laptop; they also open the original chats in the app.

## Current state
- **Repo:** https://github.com/yeknock/armenian-transcriber (local: `~/Desktop/armenian-transcriber`)
- **Files so far:** `PLAN.md` (requirements, architecture, modules + I/O, milestones M0–M6,
  risks, testing, project rules), `DECISIONS.md` (D0–D5), `.gitignore`, `requirements.txt`
  (`numpy`, `sounddevice`), `scripts/level_meter.py` (live loudness bars for two inputs).
- **Environment:** Python 3.12.3 + `venv` (`.venv`), Homebrew 7.0.10. Activate with
  `source .venv/bin/activate` in every new Terminal window.
- **Audio setup done:** BlackHole 2ch installed. Multi-Output Device "Call Output" =
  BlackHole 2ch (Primary/clock) + MacBook Air Speakers (Drift Correction ON).
  System output = Call Output; system input = MacBook Air Microphone.
- **Milestone:** M0 almost done — level-meter test not yet run/reported.

## Decisions (details + numbers in DECISIONS.md)
- **D0 Hardware:** MacBook Air **M1, 8 GB**, fanless → models together ≤ ~3–3.5 GB.
  Dev audio = MacBook mic + MacBook speakers. Bluetooth earbuds (TWS) set aside:
  their mic switches them to headset mode and can break the Multi-Output group.
  Speakers → echo (call audio also heard by the mic, may appear as `Me`); echo handling is
  out of scope; measure it later, then decide speakers vs headphones for the interview.
- **D0a Env:** system Python 3.12.3 + venv + requirements.txt (no uv).
- **D1 ASR (Decided):** `nvidia/stt_hy_fastconformer_hybrid_large_pc` (~115M, CC-BY-4.0, punctuation).
  Best open model on ArmBench-ASR on all metrics. Open sub-decision D1a: Transducer (NeMo)
  vs CTC (ONNX via `onnx-asr`) — decide by measuring. BuzzASR/armenian = offline ceiling only.
  Withdrawn: chillarmo whisper-turbo (over-fitted to Common Voice: 12.94 CV vs 82.01 Movies WER).
- **D2 VAD (Tentative):** Silero VAD v6.
- **D3 MT (Tentative):** NLLB-200 distilled, `hye_Armn → eng_Latn`; D3a 600M vs 1.3B by measuring. CC-BY-NC.
- **D4 Speaker embeddings (Open):** SpeechBrain ECAPA vs NVIDIA TitaNet; online cosine
  matching against per-speaker centroids; mic is always `Me`.
- **D5 Architecture (Tentative):** cascade, segment-based: capture → VAD → (speaker) → queue →
  ASR → MT → printer; 2 audio lanes in parallel, one shared worker.

## How we work (user's preferences)
- **Step by step:** explain first, in detail, then write one piece at a time; user reviews,
  runs it in Terminal, and commits.
- When something fails: **explain the cause first, then fix**.
- Claude writes files into the repo but **cannot run commands there** (no git, no Python) —
  the user runs everything and reports output.
- Never write shell placeholders with `< >` (zsh treats them as redirection); give real
  example values. Don't use `#` comments in commands meant to be pasted into zsh.
- Verify model/library claims against sources; record decisions with numbers. Fail loudly,
  no silent fallbacks, no extra features.

## Next step
1. Run `python scripts/level_meter.py --list`, then
   `python scripts/level_meter.py --mic N --call M` (N = MacBook Air Microphone, M = BlackHole 2ch).
2. Checks: silence → both low; speak → MIC moves, CALL stays empty; YouTube → CALL moves,
   MIC moves a little (echo). Report the `--list` output, results and dropouts count.
3. Then M1: walking skeleton (mic only → VAD → ASR → MT → terminal). Planned refinement for
   `audio/devices.py`: accept device names, not only numbers (numbers shift when devices connect).
