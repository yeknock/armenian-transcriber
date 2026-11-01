# Brief — mt

**Goal:** Armenian text → English with NLLB-200 distilled (`hye_Armn → eng_Latn`, D3), run locally with
CTranslate2 int8, and settle D3a: 600M vs 1.3B.

**Read:** `MODULES.md`, `transcriber/mt.py`, `DECISIONS.md` D0 and D3.

**May edit:** `transcriber/mt.py`, `scripts/try_mt.py`, `eval/mt_sentences.txt`, `requirements.txt` (append),
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
- [ ] all lines translated by 600M and 1.3B; the user rates each good / ok / bad
- [ ] time per line and RSS for both sizes in Status (targets: ≤ 0.8 s, ≤ 1.5 GB)
- [ ] D3a decided with these numbers
- [ ] works with Wi-Fi off

**Out of scope:** ASR, using context from earlier segments.

## Status
**In progress (2026-11-01), started in chat `05-asr`.** Code written and tested without the real model; the models
are not converted yet, so nothing is measured.

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
- `scripts/try_mt.py`: HY, EN, number of sentences and time per line; load time and peak memory; `--model`, `--beam`,
  `--threads`, `--repeat`.
- `eval/mt_sentences.txt`: 23 lines (greetings, short replies, questions, numbers, names, two-sentence lines, a long
  sentence, colloquial forms) + 4 real ASR outputs from the live call. **The clean lines need a check by the user.**
- `requirements.txt`: `ctranslate2==4.8.4`, `transformers` (already installed with NeMo).
- Tested in the test env: 15 sentence-splitting cases, all 23 lines through a tiny converted model, error cases;
  torch is not imported by this module.

**ArmBench-LLM translation chart checked (D3):** none of its open models fits the Mac; NLLB stays.

**Next:** on the Mac, `pip install ctranslate2==4.8.4`, convert 600M (command in the error message / D3), run
`python -m scripts.try_mt eval/mt_sentences.txt --repeat 3 > logs/mt_nllb-600m.txt`; later 1.3B (heavy conversion:
run with nothing else loaded); the user rates the lines → D3a.

## Contract questions
1. **transformers is used at run time** (the NLLB tokenizer). It comes with NeMo; `requirements.txt` lists it
   unpinned so mt does not depend on NeMo staying.
2. **`Translator()` takes optional `model`, `beam_size`, `threads`** (defaults work, as rule 4 asks).
