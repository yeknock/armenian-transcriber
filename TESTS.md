# TESTS

Checks come from the brief's requirements (PLAN.md §1), not from the code (Tip 4).
Module chats add their own section at the bottom.
Result: ✅ pass · ⚠️ partly done or passed with a known problem (+ note) · ❌ fail (+ note) · ⬜ not run

## Requirements (end to end)

| ID | Check | Result |
|---|---|---|
| R1 | Mic and BlackHole levels move independently (`scripts/level_meter.py`) | ✅ 2026-10-24 |
| R2a | `python main.py --list-devices` prints the input devices | ✅ 2026-11-01 Mac (HOCO W35 Max, BlackHole 2ch, MacBook Air Microphone) + test env |
| R2b | `python main.py --mic "MacBook Air Microphone" --call BlackHole` starts | ✅ 2026-11-01 Mac: live runs with NLLB-600M (2 min, 25 entries) and `--mt-model nllb-1.3b` (2.7 min, 18 entries) |
| R2c | Wrong or ambiguous device name → clear error, non-zero exit code | ✅ Mac 2026-10-30 (same `resolve_device`: wrong, ambiguous, output-only name, TESTS A2) + 2026-11-01 test env through `main.py` (wrong name, missing `--call`, same device for both) |
| R3 | CER/WER on the eval set reported | ✅ 2026-11-01 baseline on `eval/real` (3 clips, 191 words): CER 8.8 %, WER 26.7 % (EV2); more clips and call-side recordings still to add |
| R4 | English of every eval clip rated good / ok / bad by an Armenian speaker | ⚠️ 2026-11-01 text lines rated by the user: 29 lines of `eval/mt_sentences.txt` 21 good / 3 ok / 5 bad (MT4); the English of the `eval/real` audio clips not rated yet. Live: formal speech good, casual speech often wrong (D3d) |
| R5a | Mic lines are always `Me` | ✅ 2026-11-01 Mac: every mic row of both live runs is `Me` (`logs/latency.csv`); by construction in `pipeline.py` |
| R5b | Scripted call, 2 call-side people taking ≥ 10 turns → each keeps one label (accuracy %) | ⚠️ not measured yet; settings untuned (D4). First signs: the 600M run gave `Speaker 1` once then `Speaker 2` ×14; the podcast run gave 4 call-side labels in 160 s. Tool ready: `scripts/try_speakers.py` + `eval/speakers/spk_two.txt` (turns to fill) |
| R5c | A 3rd call-side person gets a new label | ⬜ |
| R6 | Every printed entry has time, speaker, HY and EN | ✅ 2026-11-01 Mac (user: layout as in the brief) + test env |
| R7a | 10-min call: latency p50 / p95 / max from `logs/latency.csv`; p95 ≤ 5 s | ⚠️ no 10-min `main.py` run yet. `main.py`: 600M 2 min max 2.62 s, 1.3B 2.7 min max 3.76 s (median 2.77 s), 0 over 5 s. `scripts/live_asr.py` (same models, no speakers): 10.8 min ASR only p95 3.38 / max 3.76 s (L2), 9 min with MT max 4.16 s (L5), 0 over 5 s |
| R7b | Both sides talking at once: p95 still ≤ 5 s | ⚠️ not tested on purpose. Replay of the busiest logged call (185 phrases, real hand-over and ASR times, pessimistic MT times): 600M max 4.47 s, 0 over 5 s; 1.3B max 5.17 s, 1 over |
| R8 | Whole run works with Wi-Fi off | ⚠️ each model alone: VAD (V14), ASR (ASR6), MT (MT7) pass with Wi-Fi off; the whole `main.py` with TitaNet not yet |

## Edge cases

| ID | Check | Result |
|---|---|---|
| E1 | 1 min of silence / room noise → nothing printed | ✅ 2026-11-01 Mac: 60 s room noise → 0 VAD segments (V5), so nothing reaches ASR or the screen |
| E2 | 30 s non-stop speech → split into several entries, each ≤ 5 s late | ✅ 2026-11-01 Mac: 35 s nonstop → pieces ≤ 9.6 s (V8), handed over ≤ 1 s after their end (V9); live calls 0 over 5 s |
| E3 | Very short reply ("Այո") → printed; does not create a new speaker | ✅ VAD keeps all 5 short replies (V7, Mac); MT gives the glossary English («Այո։» → "Yes.", MT12/MT13); a phrase < 1 s never starts a speaker (`tests/test_speakers.py`). Not yet watched in a live call |
| E4 | Ctrl+C → exits within ~1 s, no traceback | ✅ 2026-11-01 test env (`main.py`: last phrases printed, summary, exit 0; second Ctrl+C stops at once); Mac live runs ended with the summary. "~1 s" becomes ~1–2 s when a phrase is still being translated |
| E5 | Microphone permission missing → clear message naming the setting | ✅ 2026-11-01 test env (fake mic of exact zeros: message, exit 1) |
| E6 | Call audio on speakers → how often echo shows up as `Me` (measure; echo handling is out of scope) | ❌ 2026-11-01 Mac (`logs/live_asr_20261101-175249.csv`, YouTube podcast, MacBook speakers): 10 / 10 `Call` phrases also came out as `Me` (86–100 % time overlap) → use headphones (D0) |

## Module checks

(Each module chat adds its section here: audio, vad, asr, mt, speakers, eval.)

### audio (chat 03, MacBook Air M1)

"Test env" = run by Claude without real devices (generated audio / fake sound card); the rest ran on the Mac.

| ID | Check | Result |
|---|---|---|
| A1 | `python -m scripts.try_audio --list` shows only input devices (BlackHole 2ch, MacBook Air Microphone) | ✅ 2026-10-30 |
| A2 | Wrong name (`zoom`), ambiguous (`"MacBook Air"`), output-only (`"Call Output"`) → clear error, exit ≠ 0 | ✅ 2026-10-30 |
| A3 | `--selftest`: 48 / 44.1 kHz, mono / stereo, random block sizes → exact 512-sample chunks, exact start times, matches an ideal 16 kHz tone (error < 1e-3), block size has no effect, values in [-1, 1] | ✅ 2026-10-30 (Mac + test env) |
| A4 | The self-test fails if each block is resampled on its own (bug planted on purpose) | ✅ test env |
| A5 | 60 s, both sources, YouTube + two people talking: chunks within 1 %, lag < 0.1 s, 0 dropouts | ✅ 2026-10-30: 0.01 % / 0.02 %, max 59 / 46 ms, 0 |
| A6 | Callback crash or worker error → `RuntimeError` naming the source; driver overflow counted as a dropout | ✅ test env |
| A7 | Ctrl+C during `try_audio` → "Stopped early.", result printed, no traceback | ✅ 2026-10-30 |
| A8 | `record.py` writes 16 kHz mono 16-bit, exact length, correct pitch, no clicks (440 Hz tone read back); refuses an existing file and `--seconds 0`; Ctrl+C writes nothing, no traceback | ✅ test env |
| A9 | `record.py` clips from mic and BlackHole sound right | ✅ 2026-10-31 (the mic clip also has the speaker sound: echo, see E6) |
| A10 | `dropouts` stay 0 with ASR + MT running (`latency="low"` means a mic callback every 1.3 ms) | ⬜ M5 soak test |

### vad (chat 04, MacBook Air M1)

"Test env" = run by Claude on Linux with the same recordings; "Mac" = run by the user. Both gave identical cuts.

| ID | Check | Result |
|---|---|---|
| V1 | `_SileroModel` (our onnxruntime code) gives the same probabilities as Silero's official wrapper, on every WAV in `eval/audio/` and on generated audio (≤ 1e-6; actual 0.0) | ✅ 2026-10-31 Mac + test env |
| V2 | Using the VAD never imports torch (fresh process) | ✅ 2026-10-31 Mac + test env |
| V3 | Segmenter rules with a fake model (`tests/test_vad.py`, 24 tests): pre-roll, padding, end time, hysteresis, short pause kept, drops counted, early cut after 5 s in the middle of a 96 ms dip, quiet hard cut at 10 s, no overlap / no lost audio, wrong source and gaps raise | ✅ 2026-11-01 Mac + test env |
| V4 | 15 planted bugs (no pre-roll, wrong end, unsure = speech, no early cut, cut at the loudest point, …) each make at least one test fail | ✅ 2026-11-01 test env |
| V5 | 60 s room noise → 0 segments, 0 dropped | ✅ 2026-11-01 Mac |
| V6 | 5 phrases with ~3 s pauses → 5 segments; a phrase with 100–150 ms pauses inside stays one segment | ✅ 2026-11-01 Mac, listened: each phrase whole |
| V7 | Short replies (Այո, Ոչ, Հա, Լավ, Մերսի) → all 5 kept, none dropped (VAD part of E3) | ✅ 2026-11-01 Mac |
| V8 | 35 s nonstop speech → pieces ≤ 10 s (longest 9.60 s) | ✅ 2026-11-01 |
| V9 | VAD's share of latency: 0.32–0.35 s after a phrase, 0.06 s after an early cut, 0.13–0.61 s after a quiet hard cut | ✅ 2026-11-01 |
| V10 | Time per `feed()`: median 0.10 ms, max 0.41 ms on the M1 (target: a few ms) | ✅ 2026-11-01 Mac |
| V11 | Listening: every segment of `test_mic` and `call_speech` incl. both early cuts — no word, first syllable or ending cut | ✅ 2026-10-31 user |
| V12 | Listening: the 4 quiet hard cuts (`nonstop` 24.000 s, `call_interview` 9.792 / 25.280 / 34.656 s) fall between words; all segments of all 7 recordings sound right (short replies cut to just the word) | ✅ 2026-11-01 user |
| V13 | Memory: both Segmenters ~53 MB, whole `try_vad` process 78–83 MB peak, torch not loaded (budget: ≤ 50 MB per Segmenter) | ✅ 2026-11-01 test env (Mac peak not recorded) |
| V14 | No network: with networking switched off, all 24 tests pass and `try_vad` cuts as usual (MODULES rule 6) | ✅ 2026-11-01 test env |

### asr (chat 05, MacBook Air M1)

"Test env" = run by Claude without the real model (stand-ins for NeMo, tiny random models with the real libraries);
"Mac" = run by the user. Segments = the VAD's cuts in `eval/audio/segments/`. Logs in `logs/` (git-ignored).

| ID | Check | Result |
|---|---|---|
| ASR1 | `Transcriber()` loads `models/nvidia_hy_nemo/*.nemo` with NeMo (RNNT, CPU) and warms up; missing file → error with the download command | ✅ 2026-11-01 Mac + test env |
| ASR2 | Load time and memory in `.venv` (budget ≤ 1.0 GB): 9.8 s (first start after install 68 s), +1.37 GB | ⚠️ 2026-11-01 Mac: over the budget (D1a) |
| ASR3 | Time per segment (budget ≤ 0.8 s for 10 s): 0.27–0.35 s, 9.86 s segment 0.35 s, RTF 0.048 | ✅ 2026-11-01 Mac |
| ASR4 | Armenian text for ≥ 3 recordings (mic + BlackHole), checked by eye: clean phrases right, names / casual speech often wrong | ✅ 2026-11-01 user |
| ASR5 | NeMo vs onnx-asr: identical text on 18 segments, for both heads (letter for letter) | ✅ 2026-11-01 Mac |
| ASR6 | Works with Wi-Fi off (NeMo installs telemetry libraries; its log says nothing is collected) | ✅ 2026-11-01 Mac (user) |
| ASR7 | Bad input → `ValueError` (not float32, not 1-D, < 0.1 s, > 20 s, NaN); the caller's array is never changed (also checked by `try_asr` on every file) | ✅ test env + Mac |
| ASR8 | `.venv` run vs earlier NeMo run: same text on 11/11 segments | ✅ 2026-11-01 Mac |
| ASR9 | VAD tests still pass after installing NeMo into `.venv` (`python -m unittest tests.test_vad`) | ✅ 2026-11-01 Mac (user) |
| ASR10 | Competitors on the same 11 segments (D1b): whisper-turbo-hy 2.58 s, seamless 2.68 s, whisper-large-hy 45.9 s median per segment vs nvidia 0.30 s; none better by the user's judgement | ✅ 2026-11-01 Mac |
| ASR11 | Clean exit: once (2026-11-01) `try_asr` printed all results and its summary, then crashed with a segmentation fault while Python shut down; the next run exited cleanly. If it happens again: run with `python -X faulthandler ...` to see which library crashes (A–D in chat 05). Matters for E4 (clean Ctrl+C) | ⚠️ seen once, not reproduced |

**Live checks with `scripts/live_asr.py`** (mic + BlackHole → VAD → ASR, Armenian only; no translation, no speaker
labels yet). They give early numbers for R7/E6, not the final checks (those need the full program):

| ID | Check | Result |
|---|---|---|
| L1 | First Zoom call: Zoom's speaker was not "Call Output", so BlackHole stayed silent and the other side reached the program only through the room mic (all 33 phrases `Me`, badly recognised). The script now warns after 10 s of digital silence on BlackHole and in its summary | ✅ fixed 2026-11-01 (test env) |
| L2 | 10.8 min Zoom call with routing fixed: 119 `Me` + 66 `Call` phrases, 0 over 5 s; latency p50 1.35 s, p95 3.38 s, max 3.76 s (ASR only) | ✅ 2026-11-01 Mac |
| L3 | Where the time goes in L2: queue 0.00 s (p50), ASR 0.30 s; VAD hand-over `Call` 0.44 s but `Me` 1.97 s p50 / 3.32 s max (D2 "Found in live calls"). Later calls, `Me` hand-over p50 / max: 0.54 / 0.78 s (`175249`, speakers), 0.81 / 2.11 s (`180632`), 0.55 / 1.22 s (`181818`, headphones), 1.85 / 2.27 s (`194323`); `Call` 0.35–0.41 s p50 in all | ⚠️ open for M5: varies between calls, cause not verified |
| L4 | Ctrl+C: the phrase in progress is still printed, then the summary; second Ctrl+C aborts; silent mic, failed device, ASR crash, wrong / same device → clear error, exit ≠ 0 | ✅ test env (8 scenarios on real recordings) |
| L5 | Live Zoom call with MT (`live_asr.py` + NLLB-600M): latency p50 / p95 / max incl. MT, 0 over 5 s?, English understandable?, non-speech skipped | ✅ 2026-11-01 Mac, 0 over 5 s in all four logged calls (`logs/live_asr_20261101-*.csv`): `175249` speakers, 1.7 min, 30 printed, p50 1.22 / p95 2.08 / max 2.72 s; `180632` 9 min, 24 printed, 2.56 / 3.88 / 4.16 s (queue up to 2.8 s); `181818` headphones, 4 min, 46 printed, 1.17 / 1.96 / 2.06 s, 12 non-speech skipped; `194323` 6.7 min, 26 printed, 1.48 / 2.97 / 3.58 s, 5 skipped. MT per phrase median 0.35–0.88 s, max 1.34 s. English (user, chat 06): good on formal speech, bad on casual speech and on ASR mistakes (D3d) |

### mt (chats 05–06, MacBook Air M1)

"Test env" = run by Claude with a tiny random NLLB-type model (same CTranslate2 4.8.4 and transformers 5.22.1, real
conversion command); it checks the code paths, not the English. "Mac" = run by the user with the real NLLB-600M.

| ID | Check | Result |
|---|---|---|
| MT1 | Missing model → `FileNotFoundError` with the exact conversion command; bad `model` / `beam_size` → `ValueError`; non-str input → `TypeError`; `""` and punctuation-only input → `""` | ✅ 2026-11-01 test env |
| MT2 | Tokenizer gives `[hye_Armn, ..., </s>]` at load, else `RuntimeError` (legacy order planted on purpose: caught) | ✅ 2026-11-01 test env + Mac (real NLLB tokenizer passes) |
| MT3 | Every sentence of a multi-sentence line shows up in the English (lines 17, 18) | ✅ 2026-11-01 Mac (both present; line 17's 2nd sentence mistranslated, see D3a) |
| MT4 | User rates every line of `eval/mt_sentences.txt` good / ok / bad (NLLB-600M) | ✅ 2026-11-01 user: beam 1 21 / 3 / 5, beam 2 19 / 3 / 7 (`logs/mt_600m_beam*.txt`) |
| MT5 | Time: median line ≤ 0.5 s, longest line (24 words) ≤ 0.8 s, beam 2 and beam 1 (`try_mt --repeat 3`) | ⚠️ 2026-11-01 Mac, beam 1: median 0.258 s OK; longest 1.232 s OVER (21+ words: 0.70–1.23 s). Replay of the busy call with these times: max 4.17 s, 0 over 5 s (D3a) |
| MT6 | Memory: model (without torch) ≤ 1.5 GB; load time | ✅ 2026-11-01 Mac: +1.07 GB (beam 1), load 3.4 s |
| MT7 | Works with Wi-Fi off | ✅ 2026-11-01 Mac (user): all 29 lines, median 0.274 s, max 1.254 s, same as online |
| MT8 | VAD tests still pass after installing CTranslate2 (`python -m unittest tests.test_vad`) | ✅ 2026-11-01 Mac (user) |
| MT9 | Short inputs (`eval/mt_short.txt`, `--scores`, split and `--whole`): what NLLB does with one-word and non-speech inputs, and whether the score tells invented text apart (D3b) | ✅ 2026-11-01 Mac: one-word input mostly invented; joined with a neighbour right (4/4); two long sentences together: one dropped; scores overlap |
| MT10 | `make_pieces`: 11 cases (one-word sentence joins the next / the one before, long sentences stay apart, chains); 2000 random segments keep every word in order | ✅ 2026-11-01 test env |
| MT11 | `is_non_speech`: `Հովհ.`, `«ովհ.`, `Հ։`, `Հ.`, `Ա։`, `Ձ։`, `։` → True; `Ու`, `Այո։`, `5`, `15։`, `Հովհ. Լավ։`, `Ես։`, `Կապ։` → False (`Է՞` alone → True: known cost) | ✅ 2026-11-01 test env |
| MT12 | Glossary: whole-segment one word only, any punctuation / case / `և` (`Այո՜`, `Բարև։`, `Ի՞նչ։`); `translate()` = joined `translate_detailed()`; warm-up goes through NLLB | ✅ 2026-11-01 test env |
| MT13 | Mac re-run of `eval/mt_short.txt` and `eval/mt_sentences.txt` with D3b: lines 26–29 of mt_short as in `--whole`; user checks the glossary English | ✅ 2026-11-01 Mac (`logs/mt_*_d3b.txt`): 26–29 identical to `--whole`, line 30 still split (both sentences kept); of the 5 BAD lines of mt_sentences, 3 now "Yes." / "Good luck." / skipped as non-speech, 2 unchanged (colloquial idiom, garbled ASR); times unchanged; glossary English checked by the user |
| MT14 | Repetition loop (D3c): «Սպասի, սպասի։» no longer loops; `no_repeat_ngram_size` 4 changes ≤ 6 of 71 real call lines and 1 of 29 test lines (`logs/rep_*.txt`) | ✅ 2026-11-01 Mac |
| MT15 | Word lists (D3d): keys well-formed; 28 `to_written` cases (traps: «չի գալիս», «Իրան», «Ա՜», «ինչի մասին», «երեք հատ»), 13 glossary cases (incl. «Այո՞» → "Yes?", «Հաաա»), 24 non-speech cases | ✅ 2026-11-01 test env |
| MT16 | `--written` on / off on `logs/mt_live.txt` and `eval/mt_sentences.txt`: user rates every changed line (D3d) | ✅ 2026-11-01 Mac: input changed on 33 / 71 real phrases (English on 29), 5 / 29 test lines (all correct); four variants read side by side by the user, word list chosen (no line-by-line tally) |
| MT17 | NLLB-1.3B vs 600M on the same 100 lines (`--repeat 3`): time, memory, English | ✅ 2026-11-01 Mac: English changed on 70; real lines median 0.37 → 0.74 s, max 1.03 → 1.99 s; model +1.10 → +1.83 GB; user chose 1.3B (+ word list) as default (D3a) |
| MT18 | VAD 5 / 10 s vs 8 / 15 s on the podcast `spk_two.wav`, English read by the user (`eval/compare_vad_mt.py`) | ✅ 2026-11-01 Mac: 21 of 45 vs 12 of 35 phrases cut mid-speech; MT median 0.41 → 0.52 s (600M); user chose 8 / 15 (D2), **reverted** after the live call below (SP5) |

### eval (2026-11-01, MacBook Air M1)

Eval set `eval/real/`: 3 spontaneous, spoken-style Armenian recordings by the user (mic, 21 / 60 / 40 s, 191 reference
words), reference texts typed by the user (`audio-0N.txt`, committed); the MP3s and their 16 kHz WAVs in
`eval/audio/real/` are git-ignored. `eval/run_asr.py` runs each clip through the VAD and ASR as in a live call; reports
in `logs/eval_asr_*.txt`. One word = ~0.5 points of WER, so differences of 1–2 words are noise.

| ID | Check | Result |
|---|---|---|
| EV1 | `tests/test_metrics.py`: normalisation (case, ՞ ՜ ՛ removed, other marks → space, `և` = `եւ`, digits kept), corpus-level CER / WER, bad input raises (15 tests) | ✅ 2026-11-01 test env + Mac |
| EV2 | Baseline, greedy, VAD 5 / 10 s: CER 8.8 %, WER 26.7 % (per clip 21.9 / 19.8 / 39.7 %); ASR 0.27 s per phrase (median). About 12 of the 51 word errors are the reference differing from what was said («է» typed where «ա» was said ×7, «33,34» said as words, two typos): to fix in the references | ✅ 2026-11-01 Mac (`eval_asr_20261101-204134`) |
| EV3 | Beam 4 (`malsd_batch`): WER 26.2 %, CER 8.8 %, one phrase changed; ASR 0.62 / 0.98 s per phrase (D1a: rejected) | ✅ 2026-11-01 Mac (`-204211`) |
| EV4 | VAD early cut 8 s / hard cut 15 s: WER 26.2 %, CER 9.6 %; split word fixed, endings lost elsewhere (D2: rejected). Both together: WER 26.2 %, CER 9.5 % | ✅ 2026-11-01 Mac (`-204148`, `-204231`) |
| EV5 | VAD early-cut dip 96 / 160 / 224 / 320 ms (`--min-dip-ms ... --segments`): WER 26.7 / 27.2 / 26.2 / 26.7 %, CER 8.8 / 8.9 / 9.7 / 9.7 %, hand-over p50 0.06 → 0.16 s; ~3 of 51 word errors come from cuts (D2: 96 ms kept) | ✅ 2026-11-01 Mac (`-204835`) |

### speakers (2026-11-01, MacBook Air M1)

| ID | Check | Result |
|---|---|---|
| SP1 | `tests/test_speakers.py` (11 tests, made-up fingerprints): labels in order of first appearance, stable over turns, a 3rd voice gets a new label, short phrases never start or change a speaker, the threshold decides, similarity to the mean direction (not the sum), the mean follows a drifting voice, bad input raises | ✅ 2026-11-01 test env + Mac |
| SP2 | The tests catch planted bugs: 6 of 6 (two tests were too weak at first and were fixed) | ✅ 2026-11-01 test env |
| SP3 | TitaNet loads from `models/titanet_large/` and runs in the live program; time per phrase (budget ≤ 0.3 s) | ✅ 2026-11-01 Mac: median 0.18 / 0.25 s, max 0.33 / 0.53 s in the two live runs (max over the budget; latency still < 5 s) |
| SP4 | Speakers found on `spk_two.wav` (2 voices) for each threshold × min length (`scripts/try_speakers.py --speakers 2`); right group vs an offline clustering into 2 | ✅ 2026-11-01 Mac fingerprints: thresholds 0.30–0.55 find 2 (100 % right group) at any min length; 0.60–0.70 find 3–6 with short minimums. Margins: phrases ≥ 2 s own ≥ 0.66 / other ≤ 0.35; < 2 s own down to 0.04 → threshold 0.45, min_new_s 2.0 (D4). Hand-typed turns not done (labels from clustering) |
| SP5 | Live Zoom call, 3 people on the call side, VAD 8 / 15 s, threshold 0.5, min_new_s 1.0 | ❌ 2026-11-01 Mac: 12 call-side phrases → 7 speakers; new speakers came from phrases of 1.2–8.4 s, four of them ≤ 2 s → VAD reverted (D2), speaker settings to tune (D4) |
| SP6 | Live Zoom call, 3 people on the call side, with VAD 5 / 10 s, threshold 0.45, min_new_s 2.0 | ⬜ next |

### integration (2026-11-01)

| ID | Check | Result |
|---|---|---|
| I1 | `main.py` with stand-in devices and models: entries in the brief's layout, `Me` / `Speaker N`, non-speech not printed, Ctrl+C finishes the last phrases, summary, `logs/latency.csv` | ✅ 2026-11-01 test env |
| I2 | Worker crash (planted ASR error) → traceback of the real error, exit 1; silent mic → message naming the setting, exit 1; same device twice / wrong name → clear error | ✅ 2026-11-01 test env |
| I3 | Live on the Mac with headphones in "Call Output" (YouTube podcast + own voice) | ✅ 2026-11-01 Mac: 600M and 1.3B runs, 0 over 5 s (R2b, R7a) |
| I4 | `--mt-model nllb-1.3b` loads the 1.3B model; a wrong name is refused | ✅ 2026-11-01 test env + Mac run |
