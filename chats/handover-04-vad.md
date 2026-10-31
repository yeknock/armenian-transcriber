# Handover 04 — VAD module (2026-10-31 to 2026-11-01)

> Summary of the VAD chat for the next chat (goal, what was built, decisions, numbers, open items).
> This is **not** the chat export. The full, unedited transcript of this session must be
> exported separately into `chats/` as its own `.md` file (brief requirement).

## Goal
- VAD sits between the audio module and ASR: it turns each source's stream of 32 ms chunks into whole phrases (`Segment`: audio + start/end times).
- Silence and noise never reach ASR. One `Segmenter` per source (mic, call), because the model keeps its own memory per stream.
- Two "channels" are different things: left/right of one device are averaged to mono in the audio module; mic and call stay two separate streams, never mixed.

## Checked before writing code
- Silero VAD 6.2.3 (latest, MIT). Read in its source: 512 samples per call at 16 kHz, 64 samples of the previous chunk put in front, memory = (2, 1, 128) array, reset = zeros. Model file ships inside the pip package, so nothing downloads at run time.
- Problems with the official loader: `import silero_vad` runs `torch.set_num_threads(1)` for the whole program (would slow ASR and speakers); its `.jit` path uses `torch.jit.load`, deprecated in torch 2.15.
- Loudness doesn't matter: mic clip turned down 20x was still detected (215 of 217 speech chunks).
- `test_call.wav` held steady tones (~349/441 Hz), not speech. Re-recorded `call_speech.wav`: 98% speech, so BlackHole capture works.

## Decisions (made by the user)
| Question | Choice | Why |
|---|---|---|
| How to run the model | Our own ~15 lines + Silero's `.onnx` + onnxruntime | Identical scores (diff 0.0), faster, no torch import, no global thread change, no deprecated code |
| Long nonstop speech | After 5 s, the first 96 ms dip ends the phrase (cut in the dip's middle) | Old rule handed `call_speech` over 3.55 s late; now 0.06 s. 96 ms, not 64, so consonant closures inside words don't trigger it |
| 10 s with no dip | Cut at the quietest 32 ms of the last 1 s | Fluent speech keeps Silero's score >= 0.5 for 10 s+; word gaps are still 20-35 dB quieter |
| Edit `DECISIONS.md` | Allowed (D2 only) | Brief's done-list needs it |

Environment on the Mac: macOS 26.6.2, silero-vad 6.2.3, onnxruntime 1.31.1, torch 2.15.0 (pulled in by silero-vad), numpy 2.5.4.

## What was built
1. `_SileroModel` (`transcriber/vad.py`): finds `silero_vad.onnx` without importing the package, runs one chunk per call with context and memory, `reset()`, rejects wrong input. `requirements.txt`: `silero-vad==6.2.3`, `onnxruntime`.
2. `Segmenter`:
   - speech p >= 0.5, silence p < 0.35, in between keeps the state (hysteresis)
   - 192 ms pre-roll; ends after 512 ms of silence, keeps 192 ms after the speech
   - after 5 s: first 96 ms dip ends it; at 10 s: cut at the quietest chunk of the last second, the rest continues
   - < 256 ms of speech: dropped, counted in `dropped_short`
   - wrong source or a gap between chunks raises `ValueError`
   - times only from chunk timestamps: WAV and live audio behave the same (Mac and Linux gave identical cuts)
3. `scripts/try_vad.py`: table of segments with hand-over delay, `feed()` time, peak memory, one WAV per segment in `eval/audio/segments/<name>/`, `--timeline`, every setting as a flag.
4. `tests/test_vad.py`: 24 tests (fake model with chosen scores and loudness for the rules; real model vs official wrapper on recordings).

## Changes along the way
- Long-speech rule: "longest pause at 10 s" -> early cut after 5 s (latency 3.55 s -> 0.06 s); dip 2 -> 3 chunks after discussing breaths and word-internal closures.
- Blind 10 s cut -> quietest point of the last second (4 mid-word cuts in the recordings; lowering 5 s / 96 ms did not reduce them in a sweep).
- One wrong test expectation fixed (silence between two phrases belongs to neither).
- Dead code removed, later the "continue as next phrase" path came back for the quiet hard cut.
- Own mistakes caught: a file copy that wrote back old content (fixed via checksums); a segment check that compared rounded times (names now show 3 decimals).

## Measured (7 recordings, M1)
- Room noise 60 s: 0 segments. Five phrases: 5 segments. Short replies: all 5 kept. Nonstop 35 s: longest piece 9.60 s.
- Pauses inside sentences <= ~350 ms (one 512 ms), between sentences >= 1.3 s; 400-800 ms silence settings gave identical segments, so 500 ms kept (0.32 s latency).
- VAD's share of the 5 s budget: 0.32-0.35 s after a phrase, 0.06 s after an early cut, <= 1 s (0.13-0.61 s) after a quiet hard cut.
- `feed()` median 0.10 ms, max 0.41 ms on M1; load 18-30 ms; both Segmenters ~53 MB (Linux), torch never loaded.
- 15 planted bugs, all caught by the tests. Works with networking switched off.
- User listened to all segments of all recordings: no word, first syllable or ending cut.

## Documentation
- `DECISIONS.md` D2: Tentative -> Decided, with every value and the measurement behind it.
- `TESTS.md`: vad section V1-V14, all green (V13 Mac memory peak not recorded).
- `briefs/vad.md`: done-list ticked, Status, notes for other chats, contract questions.

## Notes for other chats
- Integration: never `import silero_vad`; call `flush()` at shutdown; `Segment.start` includes ~0.2 s pre-roll; MODULES.md latency line (~0.6 s) is 0.32 s measured.
- ASR: segments 0.6-10 s; call-side audio is quiet (peak ~0.09-0.14).
- Speakers: two call-side people speaking back to back with no gap can land in one segment.

## Still open
- Commit and push piece 4:
  `git add transcriber/vad.py tests/test_vad.py scripts/try_vad.py DECISIONS.md TESTS.md briefs/vad.md`
  `git commit -m "vad: quiet hard cut, tuning, D2, tests and status"`
  `git push`
- Export this chat as `chats/04-vad.md` from the Claude app (no transcript file available in this session).
- Session 1 export is also missing from `chats/` (`handover-01.md` is only a summary).
- End-to-end checks (R2-R8, E1-E6, A10) belong to the integration step.
