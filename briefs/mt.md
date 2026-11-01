# Brief — mt

**Goal:** Armenian text → English with NLLB-200 distilled (`hye_Armn → eng_Latn`, D3), run locally with
CTranslate2 int8, and settle D3a: 600M vs 1.3B.

**Read:** `MODULES.md`, `transcriber/mt.py`, `DECISIONS.md` D0 and D3.

**May edit:** `transcriber/mt.py`, `scripts/try_mt.py`, `eval/mt_sentences.txt`, `eval/mt_short.txt` (added in
chat 06 for the short-input probe), `requirements.txt` (append),
`DECISIONS.md` (D3a), `TESTS.md` (mt section), this brief.

## Contract (signature in `transcriber/mt.py`)
- `Translator()` loads once. If model files are missing it raises with the exact command that converts or downloads them.
  Model files live outside the repo (`models/` is git-ignored).
- `translate(hy_text) -> str`: one segment may hold several sentences, and every sentence must show up in the
  English. `""` → `""`. Called from one worker thread. No network after the first download.

## Verify first
- In the CTranslate2 docs: how to convert NLLB, and how to set the source language and target prefix.
- Whether NLLB drops sentences when given several at once. If it does, split them before translating.
  Watch the Armenian full stop `։` (U+0589), which people often type as an ASCII `:`. Check which one the ASR outputs.
- Licence: CC-BY-NC. It is fine for the challenge and gets mentioned in the README.

## Standalone check
```
python -m scripts.try_mt eval/mt_sentences.txt
```
`eval/mt_sentences.txt` (committed) holds ~20 Armenian lines typical of a call: greetings, questions,
numbers, names, very short replies ("Այո"), one long sentence, and one line with two sentences.
For each line the script prints HY, EN and the time, plus load time and RSS at the start.

## Done when
- [x] all lines translated by 600M; the user rates each good / ok / bad (1.3B only if 600M is not good enough:
  user's decision 2026-11-01, chat 06 — the 8 GB Mac is the limit) — beam 1: 21 / 3 / 5
- [x] time per line and memory in Status (targets: median ≤ 0.5 s, longest line ≤ 0.8 s, model ≤ 1.5 GB; the time
  targets come from the latency replay below) — 0.258 s, **1.232 s (over)**, 1.07 GB; end to end still < 5 s (D3a)
- [x] D3a decided with these numbers — 600M, beam 1
- [x] short inputs (D3b): probe `eval/mt_short.txt` run and a rule chosen — join one-word sentences, glossary,
  non-speech not printed
- [ ] works with Wi-Fi off

**Out of scope:** ASR, using context from earlier segments.

## Status
**In progress (2026-11-01), started in chat `05-asr`, continued in chat `06-mt`.** NLLB-600M converted and measured
on the Mac; D3a decided (600M, beam 1; numbers in DECISIONS). Open: short inputs (D3b), Wi-Fi-off check (MT7),
VAD tests after the install (MT8).

**The 5 s rule → MT's time budget (chat 06).** The worker does ASR, then MT, for one phrase at a time, so MT time
adds to every phrase and also to the queue wait of the phrase behind it. Replay of the logged live calls
(`logs/live_asr_*.csv`, real hand-over times and ASR times) with a fixed MT time added per phrase:

| Call | ASR only: p95 / max | + MT 0.3 s | + 0.5 s | + 0.8 s | + 1.0 s |
|---|---|---|---|---|---|
| 10.8 min Zoom call, 185 phrases (L2) | 3.38 / 3.76 s | max 4.06 s | max 4.46 s | max 5.06 s, **3 over 5 s** | **13 over** |
| 6.5 min call, 29 phrases | 2.25 / 2.28 s | 2.79 s | 3.19 s | 3.79 s | 4.19 s |

So the MODULES budget (≤ 0.8 s per segment) is not enough on its own in a busy call. Real phrases are mostly short
(268 logged ASR outputs: median 3 words, p95 16, max 24), so the targets are: **median line ≤ 0.5 s, longest line
(~24 words) ≤ 0.8 s**; `try_mt` prints both. The biggest part of the budget is still the slow mic-side VAD hand-over
(max 3.32 s, D2, TESTS L3): integration should fix that, not MT.

**Verified first (brief's list):**
- CTranslate2 4.8.4 has a macOS arm64 wheel for Python 3.12 and needs only numpy and pyyaml.
- Conversion: `ct2-transformers-converter --quantization int8 --low_cpu_mem_usage --copy_files ...` works with the
  transformers 5.22.1 that NeMo installed (tested on a tiny NLLB-type model). The official repos have every file
  copied (`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `sentencepiece.bpe.model`).
- Source language and target prefix: the CTranslate2 docs' NLLB recipe (tokenizer `src_lang="hye_Armn"`, target
  prefix `eng_Latn`, drop the first output token).
- Several sentences per segment: our ASR ends sentences with `։` and already gives segments with 2+ sentences, so
  segments are split into sentences before translating (whether NLLB would drop one is not tested; splitting makes
  it impossible).
- Licence CC-BY-NC: for the README.

**What exists:**
- `transcriber/mt.py`: `Translator(model="nllb-600m" | "nllb-1.3b", beam_size=2, threads=4)` loads
  `models/nllb_600m_ct2_int8` (or `_1.3b_`) with CTranslate2 int8 on the CPU; missing files → error with the exact
  conversion command; warm-up. `translate(text)`: splits into sentences (`split_sentences`: `։` always, `. : ! ? …`
  before a space; pieces without letters or digits are attached to the sentence before), translates them in one
  batch, joins them in order; `""` → `""`; output length capped against repetition loops.
- `transcriber/mt.py` load check (chat 06): the tokenizer must give `[hye_Armn, ..., </s>]` (the CTranslate2
  recipe); the old "legacy" order (language code at the end) still runs but translates worse, so it raises.
  Planted on purpose in the test env: caught.
- `scripts/try_mt.py`: HY, EN, number of sentences, words and time per line; load time; memory split into libraries
  (torch included) and model; supported CPU compute types; median / p95 / max against the targets; `--model`,
  `--beam`, `--threads`, `--repeat`.
- `eval/mt_sentences.txt`: 29 lines — 19 clean ones (greetings, short replies, questions, numbers, names,
  two-sentence lines, a long sentence), 4 real ASR outputs from the live call, the 3 longest real ASR outputs
  (22–24 words, the worst case for time), the one-letter segment `Հ.` the ASR really gives, and one sentence spelled
  with `եւ` and with `և` (the ASR writes `եւ`). Clean lines checked by the user (2026-11-01).
- `requirements.txt`: `ctranslate2==4.8.4`, `transformers` (already installed with NeMo).
- Tested in the test env: 15 sentence-splitting cases, all lines through a tiny converted model, error cases.
- **Memory (corrected in chat 06):** `mt.py` does not import torch itself, but transformers loads it the first time
  the tokenizer is used (~0.6 GB). In the full program NeMo has loaded torch already, so MT adds only CTranslate2
  (~30 MB), the tokenizer and the model. `try_mt` now loads torch first and reports the model separately.

**ArmBench-LLM translation chart checked (D3):** none of its open models fits the Mac; NLLB stays.

**Chat 06, after the first real run:**
- `Translator` default `beam_size=1` (D3a). New `translate_pieces(pieces)`: the lower level of `translate()` (no
  splitting), returns (English, score) per piece; score = CTranslate2's mean log-probability per token.
- `try_mt`: default beam 1; `--whole` (each line as one piece, diagnostic) and `--scores`; it stops if its output
  ever differs from `translate()`.
- `eval/mt_short.txt`: the ASR's non-speech outputs, one-word replies with and without `։`, ordinary one-word
  outputs, two-word lines and multi-sentence lines.

**Chat 06, after the short-input probe (D3b):**
- `make_pieces(text)`: the pieces sent to NLLB; one-word sentences join a neighbour, longer ones stay apart.
- `ONE_WORD` glossary (18 replies) for a segment that is one such word; `normalize_word`.
- `is_non_speech(text)`: the ASR's text for coughs / "hmm" / breaths; `translate()` → `""`.
- `translate_detailed(text) -> list[Piece]` (hy, en, how = nllb / glossary / non-speech, score); `translate()` joins
  its English. Warm-up now calls NLLB directly (the glossary would skip it).
- `try_mt` prints how each piece was translated (and the score with `--scores`).

Mac re-run with D3b done (MT13, glossary checked by the user); Wi-Fi off (MT7) and VAD tests (MT8) pass.
`scripts/live_asr.py` now also translates (user's request, chat 06: try MT on a real Zoom call before integration):
EN line, MT time in the delay breakdown, non-speech not printed but counted, CSV columns `mt_end` and `skipped`.
Live Zoom calls with MT done (with headphones: labels right; English good on formal speech, bad on casual
speech and on ASR mistakes). **D3c:** `no_repeat_ngram_size=4` against repetition loops (MT14).
**Next (user's plan, chat 06):** compare on `logs/mt_live.txt`: 600M as now, 600M + spoken→written Armenian
word list, NLLB-1.3B; then ASR beam search on the saved phrases.

**Notes for integration:** call `mt.is_non_speech(hy_text)` after ASR and skip the segment (do not print it, do not
translate it; count them in the summary). `Translator()` loads in ~3.4 s; load it with the ASR before the audio
starts. MT per phrase: ~0.10 s + 0.036 s per word (beam 1).

## Contract questions
1. **transformers is used at run time** (the NLLB tokenizer). It comes with NeMo; `requirements.txt` lists it
   unpinned so mt does not depend on NeMo staying.
2. **`Translator()` takes optional `model`, `beam_size`, `threads`** (defaults work, as rule 4 asks).
3. **MT time budget:** MODULES says ≤ 0.8 s per segment; the replay above shows that is too much when every phrase
   takes it. Proposed: median ≤ 0.5 s, longest phrase ≤ 0.8 s (integration decides and updates MODULES).
4. **`torch.set_num_threads` and CTranslate2 threads:** both use 4 threads, but ASR and MT run one after the other in
   the same worker, so they never compete.
5. **New public names** (D3b): `is_non_speech`, `make_pieces`, `Piece`, `Translator.translate_detailed`,
   `Translator.translate_pieces`; `translate()` still has the contract signature.
