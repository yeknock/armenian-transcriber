# Handover 05 — ASR module, plus the start of MT (2026-11-01)

> Summary of the ASR chat for the next chat (goal, what was built, decisions, numbers, open items).
> This is **not** the chat export. The full, unedited transcript of this session must be
> exported separately into `chats/` as its own `.md` file (brief requirement).

## Goal
- ASR turns one VAD segment (float32, 16 kHz, mono) into Armenian text with punctuation: `Transcriber().transcribe(audio) -> str`.
- Settle D1a: Transducer (RNNT) vs CTC decoder, NeMo vs ONNX (`onnx-asr`).
- Along the way (user's requests): test with real Zoom calls, compare against the best competitor models, start the MT module.

## Checked before writing code
- Model card: 16 kHz mono; two heads, RNNT (default) 9.90 / 12.32 WER and CTC 11.19 / 13.23 (Common Voice 17 / FLEURS); CC-BY-4.0; non-streaming.
- Config inside the `.nemo`: 80 log-mel bands, FastConformer encoder (8x subsampling = 80 ms frames, 17 blocks, 512 wide, full attention), RNNT = LSTM 640 + joint net, CTC = one linear layer, trained 0.7 RNNT + 0.3 CTC on clips of 0.1–20 s.
- NeMo 3.0.0 source: `change_decoding_strategy(decoder_type=...)` switches heads; `transcribe()` takes numpy arrays (wraps them without copying); `export()` writes `encoder-model.onnx` + `decoder_joint-model.onnx`. Dither only in training mode.
- onnx-asr 0.12.0 source: runs NeMo CTC and RNNT from ONNX; by default it would use CoreML on macOS (we forced CPU).
- Every NeMo dependency has a macOS arm64 wheel for Python 3.12; NeMo keeps numpy, torch, onnxruntime as they are.

## Decisions (made by the user)
| Question | Choice | Why |
|---|---|---|
| Where models live | Repo's git-ignored `models/` | Still fully local; MODULES rule 6 reworded |
| Decoder | RNNT | Fewer errors by eye; CTC doubles/merges letters |
| Runtime | NeMo (onnx-asr gave identical text, 1.5–7x faster, half the memory) | User's choice: one runtime, one `.venv`; trade-off written in D1a |
| Competitors | Tested 3 (whisper-turbo-hy, whisper-large-hy, seamless) live, none better | User wanted proof on our own audio (D1b) |
| Clean-up | Delete all other models and their code, one `.venv` | Keep the project clean |
| Next module | MT (NLLB), started in this chat | Needed for the EN line |

## What was built
1. `transcriber/asr.py`: `Transcriber(threads=4)`: NeMo, RNNT, CPU, eval mode, warm-up; input checks (1-D float32, finite, 0.1–20 s), copy before NeMo, loud error on a strange NeMo result; missing model → error with the download command.
2. `scripts/try_asr.py`: WAV files or folders → text, length, time, RTF; load time and peak RSS; `--threads`, `--repeat`; stops if the input was changed.
3. `scripts/live_asr.py` (live test before the full program): mic + BlackHole → VAD → ASR; prints time, `Me`/`Call`, Armenian and the delay split into VAD + queue + ASR; Ctrl+C finishes the last phrase; errors from any thread stop it; warns about a silent mic (permission) and a silent BlackHole (call app not on "Call Output"); `--save` keeps WAV + text per phrase in `logs/`.
4. MT start: `transcriber/mt.py` (`Translator`, NLLB via CTranslate2 int8, sentence splitting), `scripts/try_mt.py`, `eval/mt_sentences.txt` (27 lines incl. 4 real ASR outputs).
5. `requirements.txt`: `nemo_toolkit[asr]==3.0.0`, `ctranslate2==4.8.4`, `transformers`.

## Changes along the way
- Path: onnx-asr CTC first → NeMo in a separate venv (reference + RNNT export) → user chose NeMo → separate venv removed, NeMo installed in `.venv`, onnx-asr code removed.
- Live call 1: all phrases came out as `Me`. Cause: Zoom's speaker was not "Call Output", so BlackHole was silent and the other side reached the mic through the speakers. Fixed by the setting; the script now warns about it.
- Competitor check: added three models behind `--model`, tested with tiny random models first (found and fixed: Whisper 2022 config lacking language tables, a transformers notice on every phrase, Seamless's language table dropped on load). Then removed again.
- Own mistakes caught: download commands with several patterns after one `--include` (the installed `hf` takes only the first) → files named one by one; the copy tool once wrote back old file versions (caught by checksums, re-staged under new names); a test harness sent Ctrl+C to its own shell (rewritten).
- MT: CTranslate2's converter tested with transformers 5.22.1 on a tiny model before the real download; sentence splitting fixed twice (`։` without a space; punctuation-only pieces).

## Measured (MacBook Air M1)
- NeMo RNNT in `.venv`: load 9.8 s (first start after install 68–97 s), +1.37 GB (budget 1.0 GB), 0.27–0.35 s per segment, RTF 0.048.
- NeMo vs onnx-asr: identical text on 18 segments, both heads. onnx-asr RNNT 0.22 s / +0.58 GB / 1.0 s load.
- Competitors (11 segments): whisper-turbo-hy 2.58 s, seamless 2.68 s (+3.2 GB), whisper-large-hy 45.9 s median per segment vs 0.30 s.
- Live Zoom call, 10.8 min, ASR only: 119 `Me` + 66 `Call` phrases, p50 1.35 s, p95 3.38 s, max 3.76 s, 0 over 5 s. Queue 0.00 s, ASR 0.30 s; VAD hand-over `Call` 0.44 s but `Me` 1.97 s (p50).
- Checks done: Wi-Fi off works (ASR6); VAD tests still pass after the NeMo install (ASR9).

## Documentation
- `DECISIONS.md`: D1 updated; D1a (RNNT + NeMo, with the onnx-asr table) and D1b (competitors) new; D2 "Found in live calls"; D3 MT progress + ArmBench-LLM check.
- `TESTS.md`: asr section ASR1–ASR11 and live checks L1–L4.
- `briefs/asr.md`: done-list ticked, Status, notes, 4 contract questions. `briefs/mt.md`: Status "in progress".
- `MODULES.md`: rule 6 (models in `models/`), asr row and measured budget.

## Notes for other chats
- **integration:** start from `scripts/live_asr.py`. Load ASR before starting audio. Contract questions in `briefs/asr.md`: `torch.set_num_threads` is process-wide; ASR memory 1.37 GB; `MAX_SECONDS = 20`. Look into the slow mic-side hand-over (~2 s, D2) once MT adds its time. Users must set the call app's speaker to "Call Output".
- **mt:** next steps are in `briefs/mt.md` Status (install CTranslate2, convert NLLB-600M, run `try_mt`, user rates lines; 1.3B later). The user should check the Armenian of `eval/mt_sentences.txt`.
- **speakers:** NeMo and torch are installed, so TitaNet (D4) adds no new library.
- **eval:** `logs/` holds the comparison runs (`asr_*.txt`) and live sessions (`live_asr_*`), git-ignored.

## Still open
- ASR11: one segmentation fault while Python shut down after a successful `try_asr` run; not reproduced. If it returns: `python -X faulthandler ...` to find the library. Relevant for a clean Ctrl+C (E4).
- MT: install, convert, measure, rate → D3a (`briefs/mt.md`).
- Commit this handover (and the ticked ASR6/ASR9 in `TESTS.md`, `briefs/asr.md`).
- Export the full transcript of this chat into `chats/` (separate from this handover).
