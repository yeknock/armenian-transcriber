# Handover 03 — audio module (2026-10-24 to 2026-10-31)

> Summary of the audio chat for the next chat (goal, what was built, decisions, numbers, open items).
> This is **not** the chat export. The full, unedited transcript of this session is `chats/03-audio.md`.

## Goal
- The audio module is the program's ears: it lets the user pick the two input devices and captures both at once
  (requirements R1, R2).
- Output promise (`transcriber/contracts.py`): `AudioChunk`s of exactly 512 samples (32 ms), 16 kHz, mono, float32 in
  [-1, 1], with `source` (`"mic"` / `"call"`) and `start` in seconds on one session clock shared by both sources.
- Mic = your voice (MacBook Air Microphone). Call = what the Mac plays: the call app plays to the Multi-Output Device
  "Call Output", which feeds the speakers (you hear it) and BlackHole 2ch (Python records it).

## Checked before writing code
- sounddevice 0.5.6 (PortAudio, MIT), read in the installed source: callback `(indata, frames, time, status)`;
  `indata` is reused (must copy); callback exceptions are "not propagated to the main thread" and stop the callbacks;
  `stream.active` turns False after such an exception; `stop()`/`close()` ignore errors by default; default latency `"high"`.
- soxr 1.1.0 (LGPL-2.1+, macOS arm64 wheels): `ResampleStream(in_rate, out_rate, channels, dtype="float32")`,
  `resample_chunk(x, last=False)`, output length varies per call. Measured: streamed output = one-shot output exactly
  (diff 0.0), matches an ideal 16 kHz tone to ~3e-7 (delay compensated), holds back ~15 ms (48 kHz) / ~40 ms (44.1 kHz),
  overshoots to 1.17 on a full-scale square wave.

## Decisions (made by the user)
| Question | Choice | Why |
|---|---|---|
| Capture style | Callback only copies → worker thread per source does mono / 16 kHz / chunks | Brief's design; audio thread stays short |
| Resampler | soxr streaming | No clicks at block borders; fastest in its benchmark; exact timestamps |
| Values above 1.0 after resampling | Clip to [-1, 1] | An error would stop the program when someone talks loudly; hardware clips anyway |
| Thread errors | New `AudioCapture.check()` raises them; `stop()` only cleans up | Errors on audio threads otherwise vanish |
| Stream latency | `latency="low"` | Default made BlackHole deliver 85 ms blocks; low = 10 ms (mic 64 frames) |
| Self-test place | `python -m scripts.try_audio --selftest` | Inside the brief's files, no new dependency |

Full record: `DECISIONS.md` D7.

## What was built
1. `list_input_devices()`, `resolve_device(spec)` (`transcriber/audio.py`): id or part of a name, a full-name match
   wins; no match, several matches or an output-only device → `ValueError` listing the candidates.
2. `_Rechunker`: mono (average of channels) → soxr stream → exact 512-sample chunks, `start = t0 + emitted / 16000`,
   clipped to [-1, 1]. No threads, no devices.
3. `AudioCapture(source, device, session_start, out)`: device's own rate, ≤ 2 channels, `latency="low"`;
   `start()`, `stop()`, `check()`, `dropouts`, `peak`. `t0` = first callback time minus that block's length.
4. `scripts/try_audio.py`: `--list`, `--selftest` (22 checks), live check `--mic --call --seconds` with per-5 s lag.
5. `scripts/record.py`: one device → 16 kHz mono 16-bit WAV through the same `AudioCapture`; refuses an existing
   file and `--seconds ≤ 0`; Ctrl+C writes nothing.
6. `requirements.txt`: `soxr` appended.

## Changes along the way
- Two live-check "failures" were bugs in the test, not the capture: (1) counting macOS stream start/stop time
  (~0.25 s each) as missing audio → count now over first-to-last arrival; (2) measuring chunks that waited in the queue
  during `stop()` (240–370 ms "lag") → measured only while capturing. Cause (2) was reproduced with a fake slow stop
  before fixing.
- `latency="low"` was first made for the wrong reason (blamed for the 240 ms); kept because 85 ms blocks are real delay;
  code comment corrected.
- Audio MIDI Setup fixed: Primary Device = BlackHole 2ch (clock), Drift Correction on MacBook Air Speakers only, 48 kHz.
- Final review: `record.py` `--seconds 0` and Ctrl+C handling, clearer `try_audio` messages.

## Measured (MacBook Air M1)
- 60 s, YouTube on Call Output + two people talking: chunk count 0.01 % / 0.02 % off, lag max 59 ms (mic) /
  46 ms (call), 0 dropouts. First chunk after ~0.25 s; stopping both streams ~0.25 s.
- Device blocks: mic 512 frames (`high`) / 64 (`low`); BlackHole 4096 (`high`, 85 ms) / 480 (`low`, 10 ms).
- Recordings sound right; the mic also hears the speakers (echo, out of scope).
- Self-test catches a planted per-block resampler (errors ~1.0); fake-device tests: callback crash and worker error
  stop the program with a clear `RuntimeError`, overflow counted as a dropout.

## Documentation
- `DECISIONS.md` D7; `TESTS.md` audio section A1–A10 (A10 open); `briefs/audio.md` done-list ticked, Status,
  contract questions.

## Notes for other chats
- Integration: call `check()` on both captures in the main loop and once after `stop()`; `try/finally` around the loop
  that stops both (see `try_audio.py live()`); don't measure latency on chunks queued during `stop()`.
- Contract questions in `briefs/audio.md`: (1) confirm `check()`; (2) `PLAN.md` §3 thread list (audio has 2 callbacks
  **and** 2 worker threads; "2 segmenter threads" contradicts D6) and `MODULES.md` audio Decision column → D7.
- Call-side audio is quiet (peak ~0.06 in the 60 s test).
- Every chunk start comes from sample counts, so WAV files and live audio give the same times downstream.

## Still open
- A10: `dropouts` stay 0 with ASR + MT running (`latency="low"` = mic callback every 1.3 ms) — M5 soak test.
- E6: how often call audio shows up as `Me` through the speakers; then speakers vs headphones for the interview.
- Session 1 export missing from `chats/`; each self-made export misses its own final reply (originals are in the app).
- `PLAN.md` still states the one-week deadline from Oct 21.
