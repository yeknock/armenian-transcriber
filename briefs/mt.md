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
(not started)

## Contract questions
(none)
