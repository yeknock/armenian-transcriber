# DECISIONS

Status: **Decided** · **Tentative** (chosen, to be confirmed by measurement) · **Open**

---

## D0 — Hardware and environment facts (2026-10-23) — Decided
MacBook Air M1, 8 GB unified memory, fanless. Wired headphones. Call app for the
interview unknown → audio routing must work with any app.
**Consequence:** all models together must fit in ~3–3.5 GB; prefer small, single-pass models.

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
