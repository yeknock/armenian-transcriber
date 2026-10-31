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

## D2 — VAD: Silero VAD 6.2.3 run directly with onnxruntime + own segmenter rules (2026-11-01) — Decided
**Model:** `silero-vad==6.2.3` (MIT; the 2.3 MB `silero_vad.onnx` ships inside the pip package, nothing is downloaded
at run time). Verified in its source: 512 samples per call at 16 kHz, the last 64 samples of the previous chunk are put
in front, the model's memory is a (2, 1, 128) array; reset = zeros. Loudness does not matter: the mic clip turned down
20x still gave 215 of 217 speech chunks.
**Runtime: our own ~15 lines + onnxruntime 1.31.1, not the package's loader.** Same probabilities as the official
wrapper (difference 0.0, checked by a test on every recording), 0.10 ms per chunk on the M1, torch never imported.
Rejected: `load_silero_vad()` — importing `silero_vad` runs `torch.set_num_threads(1)`, which silently limits every
torch model in the program (ASR, speakers) to one CPU thread; its default `.jit` file uses `torch.jit.load`, deprecated
in torch 2.15. The version is pinned because we read the `.onnx` file from inside the package.
**Rules** (`transcriber/vad.py`, all in 32 ms chunks): speech p ≥ 0.5, silence p < 0.35, unsure in between keeps the
state (Silero's own 0.15 gap). 192 ms pre-roll before the first speech chunk; a phrase ends after 512 ms of silence and
keeps 192 ms after the last speech chunk. After 5 s, the first dip of 96 ms (3 chunks below 0.5) ends it, cut in the
middle of the dip. At 10 s with no dip, it is cut at the quietest chunk (lowest RMS) of the last 1 s and the speech after
the cut goes on. Phrases with less than 256 ms of speech are dropped and counted. Chunks from the wrong source or with a
gap raise `ValueError`.
**Why these values** (measured on 7 recordings: mic phrases, short replies, 35 s nonstop, 60 s room noise, 2 YouTube/
podcast clips through BlackHole; scripts `try_vad.py` and a parameter sweep):
- *min silence 512 ms:* pauses inside sentences were ≤ 352 ms (one 512 ms), between sentences ≥ 1.3 s. 400–800 ms gave
  identical segments on every recording, 300 ms split at the 320–352 ms pauses. 512 ms keeps a margin over in-sentence
  pauses for 0.32 s of VAD latency (0.19 s at 400 ms, 0.51 s at 700 ms).
- *early cut (5 s / 96 ms):* edited and fluent speech has no 512 ms pause for 10 s or more (`call_speech`: none ≥ 100 ms
  in 15 s). The first version cut only at 10 s, at the longest pause in the second half: the first piece of
  `call_speech` was handed over **3.55 s** after its end (of a 5 s budget). Now 0.06 s. 96 ms (not 64) because a
  consonant closure (պ, տ, կ) can be ~50–100 ms of near-silence inside a word. Sweep soft limit 2–5 s × dip 64/96/128 ms:
  hard cuts stayed at 4 in every combination; 5 s gives the fewest half-sentence pieces.
- *quiet hard cut (1 s):* in fluent speech Silero stays ≥ 0.5 (0.96–1.00) for 10 s, so no score-based rule finds the
  word gaps, but they are 20–35 dB quieter than the speech. The 4 blind 10 s cuts were all in loud speech (score ~1.00
  on both sides); the quietest chunk of the last second was −47/−61/−71/−59 dB (speech median −25/−38 dB), 0.13–0.74 s
  back. Cost: those pieces are handed over up to 1 s late (measured 0.13–0.61 s).
- *threshold 0.5/0.35, min speech 256 ms, pad 192 ms:* Silero's defaults; 60 s room noise gave 0 segments and 0 drops;
  short replies (Այո, Ոչ, …) had 0.4–0.6 s of speech, all kept. Listened to (user, 2026-10-31 / 11-01): every segment
  of all 7 recordings, incl. every early cut and the 4 quiet hard cuts — no word, first syllable or ending cut.
- *max 10 s:* the ASR contract allows up to 15 s, its time budget is set for a 10 s segment.
**VAD's share of the 5 s latency:** 0.32–0.35 s after a normal phrase, 0.06 s after an early cut, ≤ 1 s after a quiet
hard cut. **Cost:** 0.10 ms per `feed()` on the M1 (max 0.41 ms); 18–30 ms to load; both Segmenters together ~53 MB
(onnxruntime 18 MB + 25 + 10 MB, Linux measurement).
**Known limits:** an early cut keeps only ~32 ms after the speech (not 192 ms), so a last sound could be clipped; the
quietest chunk can still be a consonant closure; two call-side people speaking back to back without a gap end up in one
segment (speakers module); webrtcvad rejected (older, worse on noise).

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
