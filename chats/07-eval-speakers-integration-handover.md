# Handover 07 — docs review, ASR evaluation, speakers, the whole program, README, final tuning (2026-11-01)

> Detailed summary of session 07 (2026-11-01, 19:35 – 23:27 Asia/Yerevan), written by Claude at the end of the session
> at the user's request. This is **not** the chat export: the session's transcript file was not available in Claude's
> workspace, so a full, unedited export could not be made from inside the chat, and a copy rewritten from memory would
> not be unedited. The original conversation remains in the app (Claude Cowork) and is the full record.
> User = Yenok Martirosyan. Commits of this session: `43e5796`, `4f38b16`, `d01d4af`, `fa585a9`, `fb2bca2`, `2cbfae0`.

## Goal
- Start of the session: read the brief and every project file, find where the project stands.
- Then, as the user asked: bring all `.md` files in line with the code and re-check the code; try to improve the
  Armenian recognition; build the speaker module; build the whole program end to end; write the README; improve the
  translation; get the project ready to submit.

## Timeline (what was asked, what was done)

1. **19:35 — Read everything.** The brief (`Mathrix_AI_Coding_Challenge.docx`) line by line, all six files in
   `chats/`, `DECISIONS.md`, `TESTS.md`, `MODULES.md`, `PLAN.md`, every brief in `briefs/`, the code in `transcriber/`
   and `scripts/live_asr.py`. State found: audio, VAD, ASR, MT done; speakers, integration (`main.py`), eval and README
   not started; chats 04–06 are handovers (the user knows; the app export failed for them).
2. **19:48 — "Fix all non-corresponding things in the md files, check the code again."**
   - Docs fixed: PLAN (audio setup = headphones; thread list: 2 audio worker threads, no VAD thread; M1–M3 status;
     risks with measured numbers; speakers-vs-headphones decided), MODULES (decision column: audio D7, mt D3–D3d;
     measured VAD/MT budgets; latency line; a status column in the build order), DECISIONS (D2 later live calls;
     D3 "not yet measured" line; D4: TitaNet needs no new library; D5 "so far"), TESTS (L3 per-call hand-over times,
     L5 filled from the logged calls: 0 over 5 s in all four), briefs mt / asr / audio / vad / integration / speakers /
     eval (stale defaults, Wi-Fi box, model location, contract questions marked done).
   - Code review found **one real bug**: `scripts/live_asr.py` measured "chunk lag" also on chunks drained after
     `stop()` (they had waited ~0.25 s during stop), so its summary's lag was inflated. Fixed; with stand-ins the old
     version reported 520 ms on the call side, the fixed one 11 ms. Also: `try_vad.py` had no `--quiet-search-ms`
     flag; stale docstrings in `vad.py` and `mt.py`; two extra blank lines in `vad.py`.
   - Checks run (Linux shell on the Mac, no torch there): all files compile; 22 of 24 VAD tests (the other 2 need
     torch); `try_vad` cuts identical to before on two recordings; audio self-test passed; 30 MT-rule checks passed;
     `live_asr.py` end to end with stand-in devices and models.
3. **19:59 — "Improve the ASR? Try other ways with the NVIDIA model."** Claude's advice: measure first (no reference
   texts existed), mind the time (speakers not started). The user proposed recording clips with known text: accepted
   with one caution (read speech is easier than conversation, so speak naturally, write references as said).
4. **20:16 — Eval set and the first numbers.** The user added `eval/real/` (3 MP3s + typed references, spontaneous
   spoken-style Armenian, 21 / 60 / 40 s). Built `eval/metrics.py` (jiwer 4.0.0), `tests/test_metrics.py` (15 tests),
   `eval/run_asr.py` (each clip through the VAD and ASR exactly as live). **Baseline: CER 8.8 %, WER 26.7 %**
   (21.9 / 19.8 / 39.7 % per clip). Of the 51 word errors about 12 are the reference differing from what was said
   («է» typed where «ա» was said ×7, «33,34» said as words, two typos) — the user was asked to fix the references
   (not done yet).
5. **20:38–20:50 — Three ASR experiments, all rejected (no gain):**
   - beam search (`Transcriber(beam_size=4)`, NeMo `malsd_batch`): WER 26.2 %, one phrase changed, 2.3× slower;
   - longer VAD phrases 8 / 15 s: WER 26.2 %, CER 9.6 % (a split word fixed, endings lost elsewhere);
   - longer early-cut dip 96 / 160 / 224 / 320 ms: no gain; the phrase list showed only ~3 of 51 errors come from cuts.
   Conclusion: the remaining errors are names, rare and casual words — the model's limit, not a setting.
6. **20:50 — Speaker identification.** Verified TitaNet-Large in the installed NeMo 3.0.0 (`infer_segment` takes a
   numpy array) and its model card. Built `SpeakerMatcher` (pure numpy), the TitaNet wrapper, `SpeakerIdentifier`,
   `tests/test_speakers.py`, `scripts/try_speakers.py`. The user recorded `eval/audio/spk_two.wav` (Armenian podcast, 2
   people, 4:00, through BlackHole) and downloaded TitaNet. Labelling the turns was set aside.
7. **21:07 — "Avoid fancy things; finish the project end to end first."** Built `transcriber/output.py`,
   `transcriber/pipeline.py`, `main.py`; tested with stand-ins (entries, Ctrl+C, summary, CSV, worker crash, silent
   mic, wrong/same device).
8. **21:21 — Headphones.** `--list-devices` showed "HOCO W35 Max" (Bluetooth) as an input at 16000 Hz = headset mode.
   Advice: HOCO only for listening (in "Call Output", BlackHole primary, drift correction on HOCO); mic = MacBook Air
   Microphone in Zoom and in System Settings.
9. **21:38 — First live run works, quality "not good enough".** Log: 25 entries in 2 min, max 2.62 s; call side
   `Speaker 1` once then `Speaker 2` ×14. Claude: a different ASR won't help (D1b already tested the best open ones);
   NLLB-1.3B is the realistic translation upgrade.
10. **21:42–22:25 — NLLB-1.3B.** The user converted it (`ct2-transformers-converter … --low_cpu_mem_usage`). The second
    5.5 GB download during the conversion was explained from the installed transformers 5.22.1 source
    (`modeling_utils.py`: a background `auto_conversion` thread fetches a `model.safetensors` copy "for next time");
    the conversion itself had finished (`models/nllb_1.3b_ct2_int8/`, 1.38 GB). Compared on 100 lines; added
    `main.py --mt-model`. Live 1.3B podcast run: 18 entries, max 3.76 s, 4 call-side labels.
11. **22:32 — "Read the task again; add a README; turn the done tests green."** Requirement check; TESTS updated with
    evidence (R2a/b/c, R5a, R6, E1–E4 ✅; R4, R5b, R7a/b, R8 ⚠️; new speakers and integration sections); README.md
    written (setup, run, architecture, models + alternatives + why, results, limitations, improvements, layout,
    tools, method, licences) and verified against code, logs and DECISIONS (five claims corrected before it was saved).
12. **22:39–22:50 — Last hour on translation.** Four variants side by side (600M / 1.3B, each with and without the
    spoken→written word list); a VAD comparison on the podcast (`eval/compare_vad_mt.py`). **User's decision: VAD 8 / 15 s,
    NLLB-1.3B, word list on** → defaults switched everywhere.
13. **22:58 — Delivery check.** Brief re-read (identical to the first copy); repository public; nothing forbidden tracked;
    README's chats row changed from ✅ to ⚠️ (sessions 04–06 are handovers).
14. **23:07 — Live Zoom call, 3 people on the call side: speakers fell apart** (12 call-side phrases → 7 speakers).
    **User's decision: back to VAD 5 / 10 s, keep 1.3B + word list.** Speaker settings measured on real fingerprints
    and changed (below).
15. **23:22 — Final live call:** 6.3 min, 81 entries, **3 call-side speakers for 3 people**, max 4.64 s, 0 over 5 s.
    Final doc sweep (stale statements fixed), committed as `2cbfae0`.

## Checked before writing code (sources, not memory)
- **NeMo 3.0.0 (installed source):** RNNT beam strategies `malsd_batch` / `maes_batch`, `beam.beam_size`,
  `allow_cuda_graphs`, n-gram LM fusion (`ngram_lm_model`) and word boosting (`boosting_tree`) exist; the model file
  stores `return_best_hypothesis: false` (beam search would then return every candidate → set to true).
  `EncDecSpeakerLabelModel.infer_segment(np.ndarray)` copies the array and runs under no_grad.
- **TitaNet-Large model card:** ~23M parameters, 192-number embedding, 16 kHz mono, 0.66 % EER VoxCeleb1, CC-BY-4.0,
  trained on VoxCeleb, Fisher, Switchboard, LibriSpeech, SRE.
- **jiwer 4.0.0:** `process_words` / `process_characters` take lists (corpus level), `visualize_alignment`.
- **transformers 5.22.1:** the background safetensors download (`safetensors_conversion.auto_conversion`).
- **BlackHole licence:** GPL-3.0 (used as a separate driver, not shipped).

## Decisions (made by the user; numbers in DECISIONS.md)
| Question | Choice | Why |
|---|---|---|
| Measure ASR how | The user's own recordings with typed references (`eval/real/`) | Real spoken Armenian; read text would flatter the model |
| Beam search (D1a) | Rejected, greedy stays | WER 26.7 → 26.2 %, one phrase changed, 2.3× slower |
| Longer VAD phrases for ASR (D2) | Rejected | WER 26.2 %, CER worse; endings lost |
| Longer early-cut dip (D2) | Rejected, 96 ms stays | No gain; only ~3 of 51 errors come from cuts |
| Build order | End to end first, improve after | "Avoid fancy things"; speakers required |
| Bluetooth headphones | Listening only | Their mic = headset mode (16 kHz) |
| Translation model (D3a) | **NLLB-1.3B default**; 600M via `--mt-model nllb-600m` | Reads better on casual speech after reading 4 variants side by side |
| Spoken→written word list (D3d) | **On by default** | Changed 33 / 71 real inputs, fixed errors 1.3B alone kept; 5 / 29 clean lines changed, all correctly |
| VAD 8 / 15 s for translation (D2) | Chosen, then **reverted to 5 / 10 s** | Fewer half-sentences (12 / 35 vs 21 / 45 cut mid-speech), but the 3-person call gave 7 speakers |
| Speaker settings (D4) | **Threshold 0.45, new speakers only from phrases ≥ 2 s, a short first phrase founds nothing** | Measured margins on real fingerprints (below) |

No line-by-line rating tally was written for the translation choice (`logs/mtcmp_rate.txt`, `logs/mtcmp4_rate.txt` have
empty rating fields); the user decided after reading the outputs.

## What was built
1. `eval/metrics.py`: `normalize` (lower case; ՞ ՜ ՛ ՚ removed; other marks → space so «տեսախցիկ։Ու» stays two words;
   `և` = `եւ`; digits kept), `cer`, `wer` (corpus level), `word_alignment`. `tests/test_metrics.py` (15 tests).
2. `eval/run_asr.py`: WAVs + `--refs`; VAD → ASR as live, non-speech dropped as live; CER / WER per clip and total;
   `--align`, `--segments` (each phrase with times, hand-over delay, text), `--beam`, `--soft-max-s`, `--max-segment-s`,
   `--min-dip-ms` with several values in one model load + a summary table; report to `logs/eval_asr_<time>.txt`.
3. `transcriber/asr.py`: `Transcriber(threads=4, beam_size=1)`; beam > 1 = `malsd_batch` with
   `return_best_hypothesis=True`, `allow_cuda_graphs=False`. Default greedy unchanged.
4. `transcriber/speakers.py`: `SpeakerMatcher(threshold=0.45, min_new_s=2.0)` — mean direction per speaker; cosine ≥
   threshold joins (and updates the mean if the phrase is ≥ min_new_s); otherwise a new speaker only if ≥ min_new_s;
   shorter phrases take the closest speaker and change nothing; before any speaker exists a short phrase is labelled 0
   but stores nothing. `_TitaNet` (loads `models/titanet_large/*.nemo`, warm-up on quiet noise, checks 192 finite
   numbers, returns a unit vector; does not touch torch threads). `SpeakerIdentifier(...).identify(audio)` →
   `"Speaker N"`, `.embed()`, `.speakers_found`.
5. `tests/test_speakers.py` (11 tests). Planted bugs: 6 of 6 caught after two tests were strengthened (a short phrase
   that *matches* must not change the mean; similarity must be to the mean direction, not the sum; a drifting voice
   needs the running mean), plus the old first-phrase rule is caught by the new first-phrase test.
6. `scripts/try_speakers.py`: VAD-cuts a call-side WAV, TitaNet fingerprints once (time, RSS), cache
   `logs/speakers_<name>.npz`; with `--turns` (who spoke when, `0:00-0:14 A`): accuracy table threshold × min_new_s
   after best one-to-one pairing, mixed phrases set aside; with `--speakers N`: how many speakers each setting finds,
   similarity percentiles; `--from-cache`, `--show`. `eval/speakers/spk_two.txt`: header + the 45 phrase times as a
   labelling guide (no turns filled in).
7. `transcriber/output.py` (entry layout of the brief), `transcriber/pipeline.py` (two captures → two Segmenters fed
   by the main thread → one worker: ASR → non-speech dropped → speaker (call side) → MT → print; `logs/latency.csv`
   with `speaker_s`; `MicrophoneSilent`; summary with p50 / p95 / max, non-speech, dropouts, speakers found),
   `main.py` (`--list-devices`, `--mic`, `--call`, `--mt-model`; loads ASR, speakers, MT; Ctrl+C finishes the last
   phrases; second Ctrl+C stops at once).
8. `eval/compare_vad_mt.py`: one WAV, several VAD settings, the program's ASR + MT; each phrase with how it ended
   (pause / early cut / hard cut) and its English, then the whole English per setting; report `logs/vad_mt_<name>.txt`.
9. `scripts/try_mt.py`: default `nllb-1.3b`, `--written` on by default (`--no-written`).
10. Defaults now: VAD 5 / 10 s (`RULE_TUNING` keeps the VAD rule tests at 5 / 10 explicitly), `Translator(model=
    "nllb-1.3b", spoken_to_written=True)`, speakers 0.45 / 2.0 s.
11. `README.md` (~460 lines). `requirements.txt`: `jiwer==4.0.0`.

## Changes along the way (own mistakes and corrections)
- The copy tool from Claude's workspace to the Mac silently wrote **old cached versions** of a file (fresh timestamp,
  old content) twice; caught by checksums / file size, fixed by staging the file under a new name. Every later copy was
  verified by checksum.
- Test harness mistakes caught: a Ctrl+C timer thread that kept the process alive (non-daemon); a stale copy of
  `main.py` in the scratch folder.
- `compare_vad_mt.py` labelled a 4.8 s phrase "hard cut" (impossible) → the label now uses the phrase length.
- README draft claims corrected before saving: disk size (models are ~1.2 GB + 1.9 GB Python environment, not 4 GB of
  models), two invented counts in a sample summary, "one person split into two labels" (not known), a cut frequency,
  the first-start time; later the chats status row (✅ → ⚠️).
- Speaker settings 0.5 / 1.0 s were starting values that failed live (7 labels for 3 people); measured and replaced.

## Measured (MacBook Air M1, 8 GB)
- **ASR on `eval/real` (3 clips, 121 s, 191 words):** CER 8.8 %, WER 26.7 %; ASR 0.27 s per phrase (median).
  Beam 4: WER 26.2 %, 0.62 / 0.98 s per phrase. VAD 8 / 15: WER 26.2 %, CER 9.6 %. Dip 96 / 160 / 224 / 320 ms: WER
  26.7 / 27.2 / 26.2 / 26.7 %, CER 8.8 / 8.9 / 9.7 / 9.7 %, hand-over p50 0.06 → 0.16 s.
- **Translation, 100 lines (71 real call phrases + 29 test lines), `--repeat 3`:** 1.3B changed the English on 70;
  real lines median 0.37 → 0.74 s, max 1.03 → 1.99 s; test lines max 1.22 → 2.22 s; model memory +1.10 → +1.83 GB.
  Word list: input changed on 33 / 71 real phrases (English on 29, both models), 5 / 29 test lines (all correct).
  Replay of the busiest logged call (185 phrases, pessimistic MT times): 600M max 4.47 s, 1.3B max 5.17 s (1 over).
- **VAD for translation, podcast `spk_two.wav`:** 5 / 10 s → 45 phrases, 21 cut mid-speech; 8 / 15 s → 35, 12 cut;
  MT (600M) median 0.41 → 0.52 s.
- **Speakers, real TitaNet fingerprints of `spk_two.wav` (45 phrases, VAD 5 / 10, 0.19 s per phrase):** pairwise
  similarity two groups (different people ~0.0–0.3, same ~0.5–0.85); vs an offline 2-group clustering: phrases ≥ 2 s
  own speaker ≥ 0.66, other ≤ 0.35; phrases < 2 s own speaker as low as 0.04. Thresholds 0.30–0.55 → 2 speakers,
  100 % in the right group; 0.60–0.70 → 3–6 with short minimums.
- **Live `main.py` runs:** 600M 2 min 25 entries max 2.62 s; 1.3B podcast 2.7 min 18 entries max 3.76 s; 1.3B + list +
  VAD 8 / 15 + speakers 0.5 / 1.0 s, 3-person call: 12 call-side phrases → 7 speakers; **final settings, 3-person Zoom
  call, 6.3 min: 81 entries (43 Me, 38 call side), 3 call-side speakers (33 / 1 / 4 phrases), latency p50 1.93 s,
  p95 4.23 s, max 4.64 s, 0 over 5 s; ASR max 0.64 s, MT max 2.23 s.**

## Documentation updated
- `DECISIONS.md`: D1a (beam measured, rejected), D2 (longer phrases, dip sweep, 8 / 15 for translation chosen then
  reverted), D3 (progress line), D3a (1.3B default, heading), D3d (decided: on), D4 (built, failed live, measured,
  0.45 / 2.0 s, live check), D5 (so far).
- `TESTS.md`: legend ⚠️; R2a/b/c, R3, R4, R5a/b/c, R6, R7a/b, R8, E1–E5 updated; eval EV1–EV5; MT16–MT18; speakers
  SP1–SP6; integration I1–I4; L3, L5.
- `PLAN.md`, `MODULES.md` (status column, budgets, latency CSV format `speaker_s`), every brief's Status.
- `README.md`: new.

## Final state (commit `2cbfae0`, pushed; the GitHub repository is public)
- Program: `python main.py --mic "MacBook Air Microphone" --call BlackHole`.
- Settings: VAD 5 / 10 s (512 ms silence, 96 ms dip); ASR NVIDIA FastConformer RNNT greedy (NeMo, CPU); speakers
  TitaNet-Large, threshold 0.45, new speakers from 2 s; MT NLLB-200-distilled-1.3B int8, beam 1,
  `no_repeat_ngram_size=4`, spoken→written word list on.
- Setup: BlackHole 2ch + Multi-Output "Call Output" (BlackHole primary, headphones with drift correction), Zoom speaker
  "Call Output", mic MacBook Air Microphone, headphones (Bluetooth only for listening).

## Still open
> Update at 23:31: the user then confirmed four checks done on the Mac — each of the 3 call-side people kept one
> label, the whole program works with Wi-Fi off, a 10-minute call stayed under 5 s, 0 audio dropouts — and TESTS
> R5b, R5c, SP6, R8, R7a, A10 are green. The first three items below are therefore done.

- **Wi-Fi-off run of the whole program** (R8): each model passed offline alone, TitaNet and 1.3B never offline.
- **A 10-minute run** of `main.py` (R7a): longest so far 6.3 min, max 4.64 s — close to 5 s with 1.3B; if it goes
  over, `--mt-model nllb-600m` halves the translation time.
- **Speaker assignment not verified**: the count was right (3 for 3), whether every phrase got the right person was not
  checked (fill `eval/speakers/spk_two.txt` or record a call side with known turns, then `try_speakers.py --turns`).
- **References in `eval/real/*.txt`** to correct to exactly what was said (TESTS EV2), then rerun
  `python -m eval.run_asr eval/audio/real --refs eval/real` for the honest baseline.
- **Translation of half-sentences** (phrases cut while someone speaks): give MT the previous phrase as context — the
  next improvement with the most expected gain; n-gram LM fusion for ASR names and rare words.
- `chats/`: sessions 04–07 are handovers; `chats/01` links to two screenshots (`session-01-assets/`) not in the repo.
  Keep every original chat in the app — the interviewers open the originals.
- Not reported in the live runs: audio dropouts under full load (A10) — the summary prints them.
