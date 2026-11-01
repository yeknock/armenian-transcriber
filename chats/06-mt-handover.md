# Handover 06 — MT module (2026-11-01)

> Summary of the MT chat for the next chat (goal, what was built, decisions, numbers, open items).
> This is **not** the chat export. The full, unedited transcript of this session must be exported from the app
> into `chats/` as its own `.md` file (brief requirement). An attempt to reconstruct it by hand in this chat was
> stopped, so the app export is the only full record.

## Goal
- MT turns one segment of Armenian text into English: `Translator().translate(hy_text) -> str`, local, within the 5 s rule.
- Settle D3a (model size and decoding), then fix what real calls showed.
- Along the way (user's requests): a quick review of the whole project against the brief, MT in the live script for
  a real Zoom test, headphones, richer word lists.

## Checked first
- Review of the brief and all `.md` files: ASR done; speakers, eval, integration and README not started; chat exports
  04 and 05 are handovers only (full exports must come from the app).
- CTranslate2 4.8.4 NLLB recipe confirmed (tokenizer `src_lang="hye_Armn"`, target prefix `eng_Latn`, drop the first
  output token). Hugging Face is not reachable from the cloud container, so the real model ran only on the Mac; code
  paths were tested with a tiny random NLLB-type model and the same library versions.
- The latency budget, by replaying the logged 10.8 min Zoom call: a flat 0.8 s of MT per phrase would put 3 phrases
  over 5 s; 0.5 s keeps all under (max 4.46 s).
- `transformers` loads torch lazily (~0.6 GB): `try_mt` now reports libraries and model memory separately.

## Decisions (made by the user, numbers in DECISIONS.md)
| Question | Choice | Why |
|---|---|---|
| Model size (D3a) | NLLB-200-distilled-600M | 8 GB Mac; 1.3B only if 600M is not good enough |
| Decoding (D3a) | Beam 1 | Rated 21 / 3 / 5 (good / ok / bad) vs beam 2 19 / 3 / 7, 23 % faster |
| One-word segments (D3b) | Glossary `ONE_WORD` | NLLB invents English for one word alone («Այո։» → "I did.") |
| Coughs / "hmm" (D3b) | Not printed (`is_non_speech`) | 44 of 268 real phrases; NLLB turned them into invented sentences |
| One-word sentence inside a segment (D3b) | Joined to its neighbour (`make_pieces`) | Right with context (4 of 4); two long sentences together lost one, so those stay split |
| Repetition loops (D3c) | `no_repeat_ngram_size=4` | Changed the fewest other lines (5 of 70 call, 1 of 29 test); the loop line had cost 3.18 s |
| Speakers vs headphones (D0) | Headphones | With speakers, 10 of 10 call phrases also came out as `Me` (TESTS E6) |
| Spoken → written Armenian (D3d) | Built, **off by default** | 7 of 33 changed lines rated better so far; the other 26 to be rated first |

## What was built
1. `transcriber/mt.py`:
   - `Translator(model="nllb-600m", beam_size=1, threads=4, no_repeat_ngram_size=4, repetition_penalty=1.0,
     spoken_to_written=False)`; tokenizer order check at load (raises on the "legacy" order); warm-up through NLLB.
   - `translate()` = `translate_detailed()` joined; `translate_detailed()` returns `Piece(hy, en, how, score,
     nllb_input)` with how = nllb / glossary / non-speech; `translate_pieces()` is the NLLB call itself.
   - `split_sentences`, `make_pieces`, `is_non_speech`, `one_word_english`, `lookup_key` (collapses repeated letters).
   - Word lists: `ONE_WORD` (60; a word with ՞ gives "?"), `NON_SPEECH_WORDS` (+ rule: every word a single letter or a
     hum), `SPOKEN_TO_WRITTEN` (88), `SPOKEN_QUESTIONS` (19, keyed without ՞), `SPOKEN_PHRASES` (3), `to_written()`.
2. `scripts/try_mt.py`: per line HY, EN, how each piece was translated, words, time; libraries vs model memory;
   median / p95 / max against the targets; `--beam`, `--threads`, `--repeat`, `--whole`, `--scores`, `--no-repeat`,
   `--rep-penalty`, `--written` (prints "NLLB got:" when the input changed).
3. `eval/mt_sentences.txt` (29 lines incl. the longest real ASR outputs and an `եւ` / `և` pair), `eval/mt_short.txt`
   (30 short-input probe lines).
4. `scripts/live_asr.py` now also translates: EN line, MT time in the delay split, non-speech counted but not printed,
   CSV columns `mt_end` and `skipped`, `--save` also writes `.en.txt`.
5. `logs/mt_live.txt` (git-ignored, private): the 71 unique ASR phrases of the two saved test calls.

## Changes along the way
- Sentence splitting alone made one-word sentences come out invented → `make_pieces` joins them to a neighbour.
- Own bugs caught by tests: the glossary would have skipped the warm-up; a number-only segment («5») counted as
  non-speech; a mix like «Հ. Հմ։» did not; «Ա՜» would have become «Է՜»; the zsh loop in my command (word splitting).
- First live call: labels looked random. Cause: the podcast came out of the speakers into the mic (echo). With
  headphones in "Call Output" the labels were right.

## Measured (MacBook Air M1, NLLB-600M int8, beam 1)
- Load 3.4 s; model +1.07 GB (without torch); whole program estimate ~2.7 GB.
- Time ≈ 0.10 s + 0.036 s per word; median line 0.26 s; longest (24 words) 1.23–1.25 s, over the 0.8 s per-line
  target. End to end the replay of the busy call still stays under 5 s (max 4.17 s, pessimistic).
- Live call with MT (before headphones): 30 phrases printed, max 2.72 s, 0 over 5 s.
- Works with Wi-Fi off (MT7); VAD tests still pass after installing CTranslate2 (MT8).
- Quality: formal speech good (interview part of the headphone call); casual speech bad: spoken forms NLLB did not
  learn («ջահել», «վաբշ», «կարում», «ա» for «է») and ASR mistakes on casual speech. With the converter on, 33 of 71
  call lines got a different input, the English changed on 29.

## Documentation
- `DECISIONS.md`: D0 (headphones), D3 decided, D3a, D3b, D3c new, D3d (tentative).
- `TESTS.md`: mt section MT1–MT16, L5, E6 (measured: echo).
- `briefs/mt.md`: done-list, Status, notes for integration, contract questions 1–5.

## Notes for other chats
- **integration:**
  - Call `mt.is_non_speech(hy_text)` after ASR and skip the segment (not printed, not translated; count them).
  - Load `Translator()` with the ASR before the audio starts.
  - The slow mic-side VAD hand-over (up to 3.32 s) is the biggest risk to the 5 s rule: a long mic phrase could
    reach ~4.9 s with MT.
  - README: headphones in "Call Output" (BlackHole + headphones, Drift Correction), not the MacBook speakers; NLLB
    licence CC-BY-NC; the short-input rules and their known cost (a real one-letter reply such as «Է՞» is hidden).
  - Proposed MT budget for MODULES.md: median ≤ 0.5 s, longest phrase ≤ 0.8 s (brief contract question 3).
  - `scripts/live_asr.py` is a working start for `pipeline.py` (now with MT).
- **speakers:** still not started; it is a required feature.
- **eval:** `logs/mt_live.txt` and the saved sessions `logs/live_asr_20261101-180632/` and `-181818/` hold real
  phrases (audio + ASR + English) for CER/WER and MT checks; private, git-ignored.

## Still open
- Rate the other 26 lines in `logs/w_compare.txt`, then decide D3d (converter on by default or not).
- Step 3 of the plan: NLLB-1.3B on `logs/mt_live.txt` only if casual lines are still bad (memory ~3.7 GB for the
  whole program, ~2× MT time: test `try_mt` alone first, then one live call watching Memory Pressure).
- Step 4: ASR beam search (NeMo RNNT) on the saved phrases: fewer mistakes vs time.
- Optional: an echo warning in the live script (most `Call` phrases also appearing as `Me`).
- Commit: everything since `7ca7d0b` (D3c, D3d, word lists, docs, this handover).
- Export the full transcript of this chat from the app into `chats/`.
