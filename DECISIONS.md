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
**Speakers vs headphones decided (2026-11-01, chat 06): headphones.** Measured (TESTS E6): with the call / podcast on the MacBook speakers, every `Call` phrase was also picked up by the mic and printed again as `Me` (10 / 10), with worse audio, so worse Armenian and English. Echo handling stays out of scope (brief); the setup fix is to put headphones instead of the speakers in the "Call Output" Multi-Output Device. Wired or USB headphones are safest; Bluetooth ones only for listening, never as the microphone (headset mode, D0).

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

**Known risk:** conversational speech is hard (Movies 60.78 WER) → expect errors in live calls. Confirmed in the
first live calls (2026-11-01): clean phrases and rare words right, names and casual speech often wrong.
**D1a decided (2026-11-01):** RNNT head, run with NeMo (see D1a). **D1b (2026-11-01):** checked live against the
next three open models on ArmBench-ASR; NVIDIA kept (see D1b).
**Offline comparison only:** BuzzASR/armenian (not on ArmBench; 1.55B, too heavy for live use).

Sources: ArmBench-ASR leaderboard (Metric AI Lab); NVIDIA model card.

## D1a — ASR decoder and runtime: RNNT head, NeMo 3.0.0 on the CPU, in the project `.venv` (2026-11-01) — Decided
**The model** (read from `model_config.yaml` inside the `.nemo`): 80 log-mel bands every 10 ms, normalised per band →
FastConformer encoder (8× subsampling = one frame per 80 ms, 17 blocks, 512 wide, full attention over the segment,
so it needs whole phrases: fits the VAD) → two heads trained together (loss 0.7 RNNT + 0.3 CTC). CTC = one linear
layer, every frame decided alone. RNNT = LSTM prediction net (640) that reads the tokens already written + joint
net, ≤ 10 tokens per frame. 1024 SentencePiece tokens + blank. Trained on clips of 0.1–20 s.
**Decoder: RNNT.** On 18 VAD segments of our recordings (test_mic, five_phrases, call_speech, call_interview) RNNT
was better by eye: CTC doubles or merges letters («Մեկ,եր», «վվեց», «ընթացքումթաց», «ողանվագ» for «ողբանվագ»).
Model card: RNNT 9.90 / 12.32 WER vs CTC 11.19 / 13.23 (Common Voice 17 / FLEURS). RNNT costs ~10 % more time.
**Runtime: NeMo, chosen by the user; onnx-asr gave the same text.** Both runtimes produced identical text on all 18
segments, for both heads (letter for letter), so the ONNX files are faithful (OpenVoiceOS CTC export; RNNT head
exported by us with NeMo; their `vocab.txt` files are identical). Measured on the M1:

| Runtime, head | 9.86 s segment | 18 segments (99.3 s) | RSS added | Load (2nd start) |
|---|---|---|---|---|
| **NeMo, RNNT (chosen)** | **0.33 s** | **5.18 s** | **+1.31 GB** | **10 s** (first start after install 68–97 s) |
| NeMo, CTC | 0.29 s | 4.77 s | (same model) | |
| onnx-asr 0.12.0, RNNT | 0.22 s | 2.02 s | +0.58 GB | 1.0 s |
| onnx-asr 0.12.0, CTC | 0.12 s | 1.27 s | +0.74 GB | 1.4 s |

Honest trade-off: onnx-asr was 1.5–7× faster and used half the memory for the same text, and needs no torch. NeMo
was kept as the one runtime of the project (the checkpoint's own toolkit, no conversion step, one shared `.venv`;
the separate NeMo venv used for the comparison was removed). Cost: ASR adds ~1.37 GB (MODULES budget: 1.0 GB) and
NeMo brings ~90 packages. If memory gets tight in integration, the onnx-asr path (code and RNNT export) is in
chat 05.
**In `.venv`** (11 VAD segments of test_mic + call_interview): load 9.8 s, +1.37 GB, 0.27–0.35 s per segment (RTF
0.048); text identical to the earlier NeMo run (11/11).
**Install (rule 7):** `nemo_toolkit[asr]==3.0.0` in `.venv`; a dry run showed numpy 2.5.4, torch 2.15.0 and onnxruntime
unchanged; NeMo's dependencies pin `packaging` 24.2 and `fsspec` 2025.12.0 (not used by our modules). NeMo also
installs telemetry libraries (wandb, opentelemetry, nv-one-logger); its log says no telemetry is collected; the
Wi-Fi-off check is still open (TESTS ASR6).
**Settings:** CPU (4 torch threads; `torch.set_num_threads` is process-wide, see briefs/asr.md), eval mode (no dither,
no dropout: same audio → same text), warm-up on 1 s of silence at load, input copied before NeMo (it wraps numpy
arrays without copying), input checks: 1-D float32, finite, 0.1–20 s.
**Rejected:** onnx-asr (above); CTC (more errors); NeMo in its own venv (two environments for one project).
**Beam search measured (2026-11-01, `eval/run_asr.py` on `eval/real`: 3 spontaneous mic clips, 121 s, 191 reference
words, references typed by the user; TESTS EV3):** NeMo `malsd_batch`, beam 4, vs greedy: WER 26.7 → 26.2 %, CER
8.8 → 8.8 % — one phrase changed («էն օգնեմ» → «ելույթն եմ», still wrong for «Ենոքն եմ») — while ASR time per phrase
went from 0.27 / 0.37 s (median / max) to 0.62 / 0.98 s. **Rejected: greedy stays.** The model is already sure of its
choices; its errors are names, rare and casual words. `Transcriber(beam_size=...)` stays as an option (default 1). The
setting the checkpoint stores, `return_best_hypothesis: false`, would make beam search return every candidate, so the
option sets it to true.

## D1b — Live check against the next three open ASR models (2026-11-01) — Decided: keep NVIDIA
The user asked to test the best competitors on our own audio before going on. ArmBench-ASR (checked 2026-11-01)
still ranks NVIDIA first among open models (Combined WER 19.86); next: `facebook/seamless-m4t-v2-large` 28.94,
`Chillarmo/whisper-large-v3-turbo-armenian` 33.00, `arampacha/whisper-large-hy-2` 33.17 (Movies, the closest to a
call: 80.16 / 82.01 / 77.82 vs 60.78). All three were run with transformers 5.22.1 on the Apple GPU (float16) on the
same 11 VAD segments:

| Model | Params | Per segment, median / max | RSS added | Load |
|---|---|---|---|---|
| **nvidia (NeMo, RNNT)** | 0.1B | **0.30 / 0.35 s** | +1.37 GB | 9.8 s |
| whisper-turbo-hy | 0.8B | 2.58 / 2.87 s | +1.53 GB | 14.5 s |
| whisper-large-hy | 1.5B | 45.9 / 84.4 s | +2.60 GB | 37.3 s |
| seamless-m4t-v2-large | 2.3B | 2.68 / 3.64 s | +3.21 GB | 18.2 s |

**Result (the user judged the Armenian):** none better overall. Whisper models: misspellings, split words, invented
dashes and ellipses («Տաս նմեկ տաս ներկու…»); whisper-large is unusable for live (RTF 7.2). Seamless: fluent, but
rewrites into literary Armenian and repeats itself (call_interview/03: «ծխի հոտը չի գալիս» three times), i.e.
invents text, and needs 3.2 GB. Turbo and Seamless are 8–10× slower than NVIDIA: with translation added they would
use most of the 5 s. All three models were deleted and their code removed (it is in chat 05).
Met on the way (recorded so they are not repeated): the installed `hf` CLI takes only the first pattern after
`--include` (files must be named one by one); `arampacha/whisper-large-hy-2` has only `pytorch_model.bin` on its main
branch; 2022 Whisper fine-tunes lack the language tables new transformers needs for `language="hy"`.

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
**Longer phrases measured (2026-11-01, `eval/run_asr.py` on `eval/real`, TESTS EV4):** spontaneous speech has few pauses,
so 15 of 20 phrases were cut early (5 s) or hard (10 s), and one hard cut split a word («մաթեմատիկ։ Կեկայի»). Early cut
after 8 s and hard cut at 15 s: WER 26.7 → 26.2 %, CER 8.8 → 9.6 %. The split word was whole again, but endings were
lost at other cuts («պահին» → «պահ», «ունեմ» → «ուն») and 3 words disappeared in audio-03. **Rejected: 5 s / 10 s
kept.** The clipped endings match the first known limit above: a 96 ms dip can be the quiet end of a word.
**Longer early-cut dip measured (2026-11-01, TESTS EV5):** min dip 96 / 160 / 224 / 320 ms → WER 26.7 / 27.2 / 26.2 /
26.7 %, CER 8.8 / 8.9 / 9.7 / 9.7 %, hand-over p50 0.06 / 0.10 / 0.13 / 0.16 s. No gain: **96 ms kept.** The phrase list
(`--segments`) shows the cuts fall at clause boundaries and only ~3 of the 51 word errors come from cuts: (1) the hard cut
at 10 s split «մաթեմատիկայի» (a longer dip cannot help: no dip there); (2) after an early cut, audio the VAD scores as
silence until the next speech is dropped once it is longer than the 192 ms pre-roll, so a soft first sound can go
(«սենց» → «Ս»); (3) with a longer dip the segment ends right after its last word and the ASR dropped the last words
(«երկու, կամ երեք»). The other ~48 errors are inside phrases (names, rare and casual words, word boundaries).
**Changed for translation (2026-11-01, user's decision): early cut after 8 s, hard cut at 15 s.** The ASR does not
care (EV4), but NLLB translates each phrase alone, and a phrase cut while the person is still speaking is often half
a sentence. On the 4-min podcast `spk_two.wav`, 21 of 45 phrases were cut mid-speech with 5 / 10 s, 12 of 35 with
8 / 15 s. `eval/compare_vad_mt.py` printed both settings' English (`logs/vad_mt_spk_two.txt`, NLLB-600M: MT per phrase
median 0.41 → 0.52 s, max 1.17 s in both); the user read them and chose 8 / 15. Cost: in nonstop speech the first
words of a phrase appear later (up to ~15 s), longer phrases take longer to translate; 15 s is within the ASR's 20 s.
Defaults in `Segmenter` changed; the VAD rule tests keep 5 / 10 explicitly (`RULE_TUNING` in `tests/test_vad.py`).
**Reverted the same evening (2026-11-01, user's decision): back to 5 s / 10 s.** In the first live Zoom call with 8 / 15 s
(3 people) the call-side labels fell apart: 12 call-side phrases became 7 "speakers" (`logs/latency.csv`, 19:05). Longer
phrases more often hold two voices, whose mixed fingerprint matches nobody; the untuned speaker settings (D4) made it
worse. Translation keeps NLLB-1.3B + the word list (D3a, D3d). Fewer half-sentences for MT stays an open problem
(better: give MT the previous phrase as context, not longer phrases).
**Found in live calls (2026-11-01, chat 05, `scripts/live_asr.py`):** in a 10.8 min Zoom call the mic side was handed
over p50 1.97 s / max 3.32 s after the end of its phrases, the call side 0.44 / 0.51 s (the 0.32 s measured on
recordings). Likely cause, not yet verified: the room mic hears the other side through the speakers plus room noise,
so its score stays in the unsure band (0.35–0.5) and the 512 ms silence wait starts late. Still under 5 s with ASR
(total p95 3.38 s, max 3.76 s), but tight once translation is added → check in M5 (TESTS R7, briefs/integration.md).
**Later calls with MT (2026-11-01, chat 06 and after; TESTS L3, L5):** mic-side hand-over p50 0.54 s (speakers, 1.7 min),
0.81 s (9 min), 0.55 s (headphones, 4 min), 1.85 s (6.7 min, 19:43). So it is not always slow and the cause is still not
verified; every call stayed under 5 s (max 4.16 s).

## D3 — Translation: NLLB-200 distilled (`hye_Armn → eng_Latn`) (2026-10-23) — Decided (size and beam: D3a; short inputs: D3b)
**Why:** Built for low-resource languages; NLLB-3.3B scores spBLEU 43.0 / COMET-22 88.3 on
FLORES-200 hye→en, above GPT-4 few-shot (35.6 / 86.2). Runs locally with CTranslate2 int8.
**Rejected:** TranslateGemma (Armenian trained only en→hy, not evaluated); local LLMs
(slower, heavier, variable Armenian quality); 3.3B (too heavy for 8 GB).
**D3a decided (2026-11-01, chat 06):** 600M, beam 1 (see D3a).
**Licence note:** CC-BY-NC (research use) — acceptable for the challenge, stated in README.
**Progress (2026-11-01, chat 05):** CTranslate2 4.8.4 (macOS arm64 wheel; needs only numpy and pyyaml). Conversion
from Meta's checkpoint with `ct2-transformers-converter --quantization int8 --low_cpu_mem_usage` works with
transformers 5.22.1 (installed with NeMo; tested on a tiny NLLB-type model, identical output with and without
`--low_cpu_mem_usage`, which keeps the 5.5 GB 1.3B original from exhausting 8 GB). Recipe from the CTranslate2 docs:
tokenizer with `src_lang="hye_Armn"`, target prefix `eng_Latn`, first output token dropped. Each segment is split
into sentences first (`։` always; `. : ! ? …` before a space; `՞ ՜` sit inside words, so they never end a sentence),
translated in one batch and joined in order, so no sentence can be dropped; 4 segments of our call logs already
hold two or more sentences. Measured on the real model since: D3a.
**ArmBench-LLM check (2026-11-01):** its Translation chart (100 short English↔Armenian sentences; direction and
metric not stated) ranks general LLMs only, NLLB is not in it. The open models there do not fit an 8 GB Mac:
gemma-4-31b (0.284; ~17.5 GB at 4-bit), GLM-5 (~744B MoE), GLM-4.7-Flash (30B-A3B: all 30B in memory), gemma-3-27b,
Mistral 24B and up. gemma-3-4b would fit (~3 GB at 4-bit, estimate) but scores lowest (0.082), is twice the 1.5 GB
MT budget, and an LLM writes word by word (estimated 1–2 s per phrase vs 0.8 s). → NLLB stays.

## D3a — NLLB-200 distilled, CTranslate2 int8, greedy decoding (beam 1) (2026-11-01, chat 06) — Decided: 600M first, 1.3B the default since 2026-11-01 (below)
**Size: 600M, the user's decision.** 1.3B was not tried: it needs ~2× the memory and time on an 8 GB fanless M1
that already holds the ASR (+1.37 GB). Revisit only if 600M is not good enough in the live tests.
**Beam: 1.** Both run on the 29 lines of `eval/mt_sentences.txt` (`--repeat 3`), each line rated by the user:

| | GOOD / OK / BAD | Median / p95 / max per line | Longest line (24 words) | Model memory | Load |
|---|---|---|---|---|---|
| **beam 1 (chosen)** | **21 / 3 / 5** | **0.258 / 0.908 / 1.232 s** | 1.232 s | +1.07 GB | 3.4 s |
| beam 2 | 19 / 3 / 7 | 0.334 / 1.143 / 1.433 s | 1.433 s | +1.16 GB | 3.8 s |

Beam 1 was rated better or equal on every line (4 lines one grade better) and is 23 % faster (median ratio 0.77).
Clean sentences, numbers, names, places and the long sentence: GOOD. `եւ` and `և` give the same English.
Time ≈ 0.10 s + 0.036 s per word (fit on beam 1).
**5 s rule:** the per-line target "longest line ≤ 0.8 s" is **missed** by lines of 21+ words (0.70–1.23 s). End to end it
still fits: replaying the busy 10.8 min Zoom call (185 phrases, real hand-over and ASR times) with MT time by
segment length, pessimistic (a 10 s segment costs the worst line, 1.23 s): p95 3.88 s, max 4.17 s, 0 over 5 s.
Thin spot: a 10 s mic phrase with the worst mic hand-over seen (3.32 s) + ASR 0.35 s + MT 1.23 s ≈ 4.9 s, so the slow
mic-side hand-over (D2, TESTS L3) must be fixed in integration.
**Memory:** the model adds ~1.07 GB (peak, measured apart from torch, which NeMo loads anyway); whole program
estimate ~2.7 GB (budget ~3.5 GB).
**Found: short inputs.** NLLB invents text for one-word inputs: «Այո։» → "I did.", «Հ.» → "C. What is the meaning
of this?", and «Հաջողություն։» split off as its own sentence → "What is the meaning of life?". This matters live:
33 % of 268 real ASR phrases are one word, and 44 of them are the ASR's output for coughs or "hmm" (`Հովհ.` 22×,
`Հ։` 13×, …). Colloquial «Ո՞նց ես, ի՞նչ կա չկա» → "Who are you, what's not there?" (BAD). Probe: `eval/mt_short.txt`
(D3b).

**Changed (2026-11-01, user's decision): NLLB-200-distilled-1.3B is the default** (`--mt-model nllb-600m` keeps 600M).
Converted with the same command (`--low_cpu_mem_usage`; transformers then starts a background download of a
`model.safetensors` copy, not needed). On 100 lines (71 real call phrases + 29 test lines) the English changed on 70;
time ~2× (real call lines: median 0.37 → 0.74 s, max 1.03 → 1.99 s; test lines max 1.22 → 2.22 s); model memory +1.10
→ +1.83 GB, whole program ~3.5 GB (estimate). Replay of the busiest logged call (5 / 10 s VAD, pessimistic MT times):
max 4.47 → 5.17 s, 1 of 185 phrases over 5 s. Live, `main.py` with 1.3B (2.7 min): max 3.76 s, 0 over 5 s. Chosen with
D3d (below) after reading the four variants side by side; to watch in long calls (R7a).

## D3b — Short inputs: one-word sentences stay with a neighbour, a one-word glossary, non-speech not printed (2026-11-01, chat 06) — Decided
**Probe** (`eval/mt_short.txt`, 30 lines, beam 1, `try_mt --scores`, split vs `--whole`; logs `logs/mt_short_*.txt`):
- *A one-word sentence inside a longer segment* is right when NLLB sees it with its neighbour, wrong alone:
  «… կզանգեմ քեզ։ Հաջողություն։» → "… tomorrow. Good luck." (split: "What is the meaning of life?"); «Այո։ Վաղը կգամ։» →
  "Yes. I will be there tomorrow." (split: "I did."); «Մել։ Շատ եմ …» → "Mel: I'm really …" (split: "I'm not going to
  lie."). NLLB kept every sentence in these 4 lines. But given **two long sentences** at once it dropped one (line 30:
  only the second came out). → **`make_pieces`: one-word sentences are joined to the next sentence (or the one
  before); longer sentences stay split.**
- *A segment that is one word* has no neighbour. NLLB got most common replies wrong: «Այո։» "I did.", «Ոչ» "What is
  it?", «Հա։» "I'm going to go.", «Մերսի։» "I'm going to tell you.", «Ալո։» "I'm going to be a little late."; ordinary
  nouns were right («Սպիտակ։» "White.", «Գիրք։» "The book."). Leaving out `։` did not help. → **`ONE_WORD` glossary**
  (user's choice): 18 common replies, used only when the whole segment is that word (after `normalize_word`: letters
  only, lower case, `և` = `եւ`); every other word still goes to NLLB. A deliberate rule-based patch for a measured
  weakness; it costs 0 ms.
- *Non-speech*: the ASR's text for coughs / "hmm" / breaths (`Հովհ.` 22×, `Հ։` 13×, `Հ.` 5×, `«ովհ.` 3×, single
  letters; 0.6–1.9 s, mostly quiet, both sides) became invented sentences («Հ.» "C. What is the meaning of this?",
  «Հովհ.» "John: I know."). → **`is_non_speech`** (user's choice: don't print them): every word has fewer than 2
  letters, or every word is one of the two "hmm" spellings, and no digit. `translate()` gives `""`; the pipeline
  should skip the segment (integration). Cost: a real one-letter reply said alone («Է՞») is hidden.
- *Scores do not separate invented text*: one-word inputs scored −0.86 to −1.45 whether right or wrong ("White."
  −0.98, "I'm not sure." −1.35); clean sentences −0.36 to −0.51. Not used as a filter.
**Still wrong (README limitation):** colloquial phrases («Ո՞նց ես, ի՞նչ կա չկա» "Who are you, what's not there?") and
garbled ASR input, which NLLB turns into fluent but wrong English.

## D3c — Against repetition loops: `no_repeat_ngram_size=4` (2026-11-01, chat 06) — Decided
**Found in the headphone call:** «Սպասի, սպասի։» → "Wait, wait, wait, …" ×15. The length cap (2 × input tokens + 10)
stopped it too late, and the loop also cost **3.18 s** of MT for a 2-word phrase (a 5 s rule risk).
**Test:** the 71 unique ASR phrases of the two saved test calls (`logs/mt_live.txt`, git-ignored: private) and the 29
lines of `eval/mt_sentences.txt`, each config compared line by line with no setting (beam 1):

| Setting | Loop line | Other lines changed (call / test) | Max MT time (call) |
|---|---|---|---|
| none | "Wait, wait, …" ×15 | — | 3.18 s |
| **no_repeat_ngram_size 4 (chosen)** | "Wait, wait, wait, what's going on?" | **5 of 70 / 1 of 29** | 1.64 s |
| no_repeat_ngram_size 3 | "Wait, wait, wait. What are you doing?" | 13 / 2 (e.g. "we all have preference", "don' t") | 1.12 s |
| repetition_penalty 1.2 | "Wait, wait. I'm going to go with you." | 33 / 8, several drop part of the sentence | 1.05 s |

With 4 the other changes are small rewordings («It's good. It's all right.»); one line lost its last two words
("what context") and one long garbled line got shorter. Penalty 1.2 also removed the "you bastard" for «վաբշ», but it
changed half of all lines and dropped content, which breaks "every sentence must show up".
**Still:** the loop line gets an invented ending ("what's going on?"): the short-input weakness (D3b), not a loop.

## D3d — Spoken → written Armenian before NLLB; richer word lists (2026-11-01, chat 06) — Decided: on (2026-11-01)
**Why:** in the headphone call, formal speech translated well, casual speech badly: NLLB learned mostly written
Armenian («ջահել ժամանակ» → "in the Holocaust", «վաբշ» → "you bastard", «չես կարում» read as "sew", «Նորմալ գնում
ա» → "I'm going to go normal"). In 421 real ASR phrases: «ա» (is) 65×, «էդ» 25×, «էս» 20×, «ոնց» 16×, «խոսա» 16×.
**What (`transcriber/mt.py`):** `to_written()` changes only NLLB's input (the HY line keeps the ASR text):
`SPOKEN_PHRASES` (3, e.g. «ինչ կա չկա» → «ինչ նորություն կա»), `SPOKEN_QUESTIONS` (19, keyed by the word without ՞,
so the mark can be anywhere: «ո՞նց» → «ինչպե՞ս», «ինչի՞» → «ինչո՞ւ»), `SPOKEN_TO_WRITTEN` (88 words), «չի» → «չէ» at a
clause end. Words with a colliding written meaning are left out (իրան, արա, մենակ, կանգնի, սպասի, ինչի without ՞,
էլի, …). Kept although it can collide: «կարում» (also "sews"). Off by default (`spoken_to_written=False`) until measured — on since 2026-11-01 (below).
Also widened at the user's request: `ONE_WORD` 18 → 60 (with ՞ the English ends in "?": «Այո՞» → "Yes?"),
`NON_SPEECH_WORDS` + hesitation sounds; `lookup_key()` collapses repeated letters («Հաաա» → հա, «ըըը» → ը), and a
segment is non-speech when every word is a single letter or a hum («Հ. Հմ։»).
**Decide by:** `try_mt --written` vs without, on `logs/mt_live.txt` (71 real phrases) and `eval/mt_sentences.txt`;
the user rates every changed line better / worse / same.
**Measured and decided (2026-11-01, after chat 06):** on the 71 real call phrases the word list changed NLLB's input on
33 and the English on 29 (with 600M and with 1.3B); on the 29 test lines it changed 5 inputs, each correctly («ա» → «է»,
«էն» → «այն», «խոսա» → «խոսիր»); no time cost. Examples: «ջահել ժամանակ» "in the Holocaust" → "when they were
younger"; «թե որ թվերին ա ապրել» "what numbers you lived in" → "… he lived in". Four variants side by side
(`logs/mtcmp4_rate.txt`: 600M, 1.3B, each with and without the list); the user chose **1.3B + word list** after reading
them (no line-by-line tally was written). `Translator(spoken_to_written=True)` is now the default.

## D4 — Speaker embeddings (2026-10-23) — Tentative: TitaNet-Large, threshold 0.45, new speakers from 2 s (measured on one podcast)
Candidates: SpeechBrain ECAPA-TDNN (`spkrec-ecapa-voxceleb`, Apache-2.0, 0.80 % EER VoxCeleb1)
vs NVIDIA TitaNet (comes with NeMo, which D1a chose: no new library). Speaker embeddings are largely
language-independent; a 5-language zero-shot study found the two roughly equal.
Method: online cosine matching against per-speaker centroids; mic side is always `Me`.
Decide in M4.
**Built (2026-11-01, after chat 06):** TitaNet-Large (`nvidia/speakerverification_en_titanet_large`, model card:
23M parameters, 192-number fingerprint, 16 kHz mono, 0.66 % EER VoxCeleb1, CC-BY-4.0; trained on English incl.
telephone speech) through NeMo's `infer_segment` — no new library. `SpeakerMatcher`: mean direction per speaker,
cosine >= threshold joins, else a new speaker only if the phrase is >= min_new_s; shorter phrases take the closest
speaker and never change one; first phrase = Speaker 1. **Starting values 0.5 / 1.0 s, not measured yet (replaced below by 0.45 / 2.0 s):** the user
chose to finish the program end to end first (2026-11-01). To tune: fill `eval/speakers/spk_two.txt` (2-voice podcast,
45 phrases) and run `scripts/try_speakers.py` (threshold x length table). ECAPA stays the fallback.
**Failed live, then measured (2026-11-01):** a Zoom call with 3 people on the call side (VAD 8 / 15 s) gave 12 call-side
phrases → 7 "speakers"; four new speakers came from phrases of 1.2–2.0 s (TESTS SP5). Real TitaNet fingerprints of the
2-voice podcast `spk_two.wav` (45 phrases, VAD 5 / 10 s, 0.19 s per phrase; `try_speakers.py --speakers 2`): pairwise
similarities split into two groups (different people ~0.0–0.3, same person ~0.5–0.85). Against an offline clustering of
all phrases into 2 groups: phrases ≥ 2 s match their own speaker's mean at ≥ 0.66 and the other's at ≤ 0.35; phrases
< 2 s match their own speaker as low as 0.04 — short phrases give unreliable fingerprints. Every threshold 0.30–0.55
found 2 speakers here, 100 % in the right group, so the podcast alone does not decide the value; it sets the margins.
**Chosen: threshold 0.45** (middle of 0.35 … 0.66, ~0.1 margin both ways for worse call audio), **min_new_s 2.0 s**
(short phrases never start or change a speaker), and a short **first** phrase no longer founds Speaker 1 (it is
labelled 1 but the first phrase ≥ 2 s sets the fingerprint) — in the live call the 2.0 s first phrase founded a
Speaker 1 that nothing matched again. **Live check (2026-11-01 23:22, 6.3 min, 3 people on the call side):** 38 call-side
phrases → 3 speakers (33 / 1 / 4), latency max 4.64 s, 0 over 5 s (TESTS SP6). Not verified: which person each phrase
really was.

## D5 — Architecture: cascade, segment-based (2026-10-23) — Tentative
VAD → (speaker) → ASR → MT, one shared worker. Streaming ASR rejected: much more complex
and not needed when the deadline is 5 s after the phrase ends. Joint speech-to-translation
model rejected: no light enough option for Armenian on 8 GB, and less modular.
**So far (2026-11-01):** `scripts/live_asr.py` runs this cascade without speakers (one worker: ASR, then MT) in live
Zoom calls; every phrase stayed under 5 s (TESTS L2, L5). Decided only once speakers and the 10-min soak test are in.

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
