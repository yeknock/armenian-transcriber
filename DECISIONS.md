# DECISIONS

Status: **Decided** · **Tentative** (chosen, to be confirmed by measurement) · **Open**

---

## D0 — Hardware and environment facts (2026-10-23) — Decided
MacBook Air M1, 8 GB unified memory, fanless. Development audio: MacBook Air mic + built-in speakers.
Bluetooth earbuds set aside (their mic switches them to headset mode and can break the Multi-Output
group). Speakers cause echo (call audio picked up by the mic, may show as `Me`); echo handling is out
of scope — measure it (TESTS.md E6), then choose speakers vs headphones for the interview. Call app for the
interview unknown → audio routing must work with any app.
**Consequence:** all models together must fit in ~3–3.5 GB; prefer small, single-pass models.

## D0a — Python environment: system Python 3.12.3 + `venv` + `requirements.txt` (2026-10-23) — Decided
**Why:** already installed; every chosen library supports 3.12; built-in `venv` means no extra
tool to install or explain. `uv` rejected only because it adds a tool we don't need.
Repo: https://github.com/yeknock/armenian-transcriber

## D1 — ASR model: `nvidia/stt_hy_fastconformer_hybrid_large_pc` (2026-10-23) — Decided
**Why:** Best open model on ArmBench-ASR across all metrics (WER, CER, normalised variants).
Clearly best on domains it was not trained on:

| WER % | NVIDIA | Next best open |
|---|---|---|
| News | 23.55 | 35.18 (omniASR-LLM-3B) |
| Poems | 31.28 | 43.93 (Seamless M4T v2) |
| Movies | 60.78 | 75.04 (cast/whisper-large-v3-mwa-hy) |
| Combined | 19.86 | 28.94 (Seamless M4T v2) |

~115M parameters → fits 8 GB alongside translation. Single-pass decoding (no token-by-token
generation) → low latency and low hallucination risk. Outputs punctuation. CC-BY-4.0.
Trained on 296 h of Armenian (Common Voice 17, FLEURS, audiobooks, proprietary corpora).

**Rejected:**
- Seamless M4T v2 large — ~2.3B params, too heavy for 8 GB, CC-BY-NC.
- Whisper fine-tunes — e.g. chillarmo/whisper-large-v3-turbo-armenian is over-fitted to
  Common Voice (12.94 CV vs 82.01 Movies WER); hallucination risk.
- omniASR (all sizes), MMS — much higher WER.
- Cloud models (ranks #1–10) — forbidden by the brief.

**Known risk:** conversational speech is hard (Movies 60.78 WER) → expect errors in live calls.
**Sub-decision still open (D1a):** Transducer decoder (NeMo) vs CTC decoder (ONNX, `onnx-asr`).
Decide in M3 by CER/WER + speed on our own clips.
**Offline comparison only:** BuzzASR/armenian (not on ArmBench; 1.55B, too heavy for live use).

Sources: ArmBench-ASR leaderboard (Metric AI Lab); NVIDIA model card.

## D2 — VAD: Silero VAD v6 (2026-10-23) — Tentative
**Why:** ~2 MB, MIT licence, 512-sample (32 ms) chunks at 16 kHz, a few ms per chunk on CPU,
robust to noise. webrtcvad rejected: older, worse on noise.
**To tune in M5:** threshold, min silence (~400–800 ms), pre-roll, max segment length (~10–15 s).

## D3 — Translation: NLLB-200 distilled (`hye_Armn → eng_Latn`) (2026-10-23) — Tentative
**Why:** Built for low-resource languages; NLLB-3.3B scores spBLEU 43.0 / COMET-22 88.3 on
FLORES-200 hye→en, above GPT-4 few-shot (35.6 / 86.2). Runs locally with CTranslate2 int8.
**Rejected:** TranslateGemma (Armenian trained only en→hy, not evaluated); local LLMs
(slower, heavier, variable Armenian quality); 3.3B (too heavy for 8 GB).
**Open (D3a):** 600M vs 1.3B — decide in M3 by speed + manual quality rating.
**Licence note:** CC-BY-NC (research use) — acceptable for the challenge, stated in README.

## D4 — Speaker embeddings (2026-10-23) — Open
Candidates: SpeechBrain ECAPA-TDNN (`spkrec-ecapa-voxceleb`, Apache-2.0, 0.80 % EER VoxCeleb1)
vs NVIDIA TitaNet (comes with NeMo if D1a picks NeMo). Speaker embeddings are largely
language-independent; a 5-language zero-shot study found the two roughly equal.
Method: online cosine matching against per-speaker centroids; mic side is always `Me`.
Decide in M4.

## D5 — Architecture: cascade, segment-based (2026-10-23) — Tentative
VAD → (speaker) → ASR → MT, one shared worker. Streaming ASR rejected: much more complex
and not needed when the deadline is 5 s after the phrase ends. Joint speech-to-translation
model rejected: no light enough option for Armenian on 8 GB, and less modular.

## D6 — Module split and contracts (2026-10-24) — Decided
Flat package `transcriber/`, one file per module (audio, vad, asr, mt, speakers) plus `pipeline.py`,
`output.py`; `main.py` is the CLI. Shared types in `transcriber/contracts.py`; each module's interface is
written in its file before it is built. Each module is built in its own chat from `briefs/<module>.md`.
Rules (MODULES.md): modules import only `contracts`; only `pipeline.py` wires them; the VAD `Segmenter` is
push-based with no threads or clock reads, so WAV-file tests behave exactly like live audio; only
`AudioCapture` may own a thread.
**Why:** Tip 3 — each module can be tested alone with WAV files or text; chats touch different files, so
they can run in parallel without conflicts.
**Rejected:** one sub-package per module (earlier PLAN §4 draft) — more files, no benefit at this size;
a Git branch per module — all chats share one working folder, so switching branches would change files
under another chat. Shared-types file is not named `types.py`: it would hide Python's built-in `types`
module when a script runs from inside the package.

## D7 — Audio capture: sounddevice callback + worker thread, soxr streaming resampler, `latency="low"` (2026-10-30) — Decided
**Capture:** `sounddevice` 0.5.6 (PortAudio, MIT; already proven by the M0 level meter). The callback only copies
each block onto a queue; a worker thread mixes to mono, resamples and cuts 512-sample chunks. Errors on those threads
do not reach the main thread (sounddevice docs), so `AudioCapture.check()` raises them (contract question in
`briefs/audio.md`). Rejected: a blocking `read()` loop — simpler errors, but a late reader overflows PortAudio's small buffer.
**Resampler:** `soxr` 1.1.0 (`ResampleStream`, LGPL-2.1+, wheels for macOS arm64). Measured: streamed output equals
one-shot resampling exactly (difference 0.0) for random block sizes, and matches an ideal 16 kHz tone to ~3e-7, so
no clicks at block borders and `start = t0 + n / 16000` is exact; hold-back ~15 ms (48 kHz) / ~40 ms (44.1 kHz).
Rejected: resampling each block alone (clicks — the self-test catches it), `scipy.signal.resample_poly` (no stream
state; we would write the error-prone part ourselves), `samplerate` (slower), `torchaudio` (needs torch), opening the
device at 16 kHz (unverified Core Audio behaviour; would change BlackHole's rate under "Call Output").
**Clipping:** the resampler overshoots on full-scale input (1.17 for a full-scale square wave); output is clipped to
[-1, 1] as the contract promises. Raising an error instead would stop the program whenever someone talks loudly; the
hardware clips at ±1 already.
**`latency="low"`:** with sounddevice's default `"high"`, BlackHole delivers 4096-frame blocks (85 ms), so call audio
reaches us up to 85 ms later; `"low"` gives 480 frames (10 ms); the mic goes from 512 to 64 frames. Live 60 s check
after the change: max lag 59 ms mic / 46 ms call, 0 dropouts. **Risk:** many more callbacks → watch `dropouts` under
full load (TESTS A10). Note: the 240–370 ms "lag" first seen came from the test measuring chunks that waited
during `stop()` (~0.25 s), not from the capture; the test now measures only while capturing.
**Audio setup fact (confirms D0):** "Call Output" = BlackHole 2ch as Primary (clock) + MacBook Air Speakers with
Drift Correction; 48 kHz.
