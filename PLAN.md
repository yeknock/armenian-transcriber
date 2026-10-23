# PLAN — Live Armenian Transcription → English Translation

## 1. Goal

A Python terminal program that listens to a live call, transcribes spoken Armenian,
translates it to English and prints each segment labelled by speaker — within 5 s.

**Success criteria (from the brief):**

| # | Requirement | How we check it |
|---|---|---|
| R1 | Captures mic + system audio at the same time | Both level meters move independently |
| R2 | User picks input devices (list + CLI flags) | `--list-devices`, `--mic`, `--call` work |
| R3 | Armenian speech → Armenian text | CER/WER on our eval set |
| R4 | Each segment translated to English | Manual "understandable?" rating on eval set |
| R5 | Mic = `Me`; call side = `Speaker 1/2/…`, stable for the session | Scripted 2-person call, label accuracy |
| R6 | Live output: time, speaker, HY, EN | Visual check |
| R7 | ≤ 5 s from end of phrase to English line | Logged latency: p50 / p95 / max |
| R8 | Everything local, no cloud APIs | Run with Wi-Fi off |

Out of scope: GUI, installer, echo handling, speaker names, cross-session memory,
saving transcripts, non-Armenian input.

## 2. Constraints

- **Hardware:** MacBook Air **M1, 8 GB** unified memory, fanless (throttles under sustained load).
- **Memory budget:** all models together ≤ ~3–3.5 GB (macOS + call app use the rest).
- **Audio:** wired headphones; BlackHole 2ch + Multi-Output Device; call app unknown → setup must work for any app.
- **Time:** ~20 h total, deadline one week from the brief (Oct 21, 2026).
- **Repo:** never commit model weights, audio recordings or keys.

## 3. Architecture (cascade, segment-based)

```
Mic ────────► Capture ─► VAD segmenter ─► label "Me" ─────────────┐
                                                                  ├─► Queue ─► ASR (hy text) ─► MT (en text) ─► Printer
BlackHole ──► Capture ─► VAD segmenter ─► Speaker identifier ─────┘
```

Threads: 2 audio callbacks (copy only) · 2 segmenter threads · 1 worker (ASR + MT) · main thread (printer, Ctrl+C).
Models are loaded once at start-up.

**Core data object**

```python
@dataclass
class Segment:
    source: str          # "mic" | "call"
    start: float         # seconds since session start
    end: float           # seconds since session start (latency clock starts here)
    audio: np.ndarray    # float32, 16 kHz, mono
    speaker: str | None = None
    hy_text: str | None = None
    en_text: str | None = None
```

## 4. Modules — inputs and outputs

| Module | Input | Output | Notes |
|---|---|---|---|
| `audio/devices.py` | — | device list; validated device ids | Fails loudly on a wrong id |
| `audio/capture.py` | device id | queue of 16 kHz mono float32 frames (512 samples) + timestamps | Callback only copies; resampling in its own thread |
| `vad/segmenter.py` | frames | `Segment` (audio, start, end) | Silero VAD; params: threshold, min silence, pre-roll, max length |
| `speakers/identifier.py` | call-side `Segment` | speaker label | Embeddings + online cosine matching; mic side → `Me` |
| `asr/transcriber.py` | float32 16 kHz audio | Armenian text | NVIDIA FastConformer (hy) |
| `mt/translator.py` | Armenian text | English text | NLLB-200 distilled |
| `pipeline.py` | config | runs threads, queue, latency log | The only place that wires modules together |
| `output.py` | finished `Segment` | terminal lines | Single printer thread |
| `main.py` | CLI flags | — | `--list-devices --mic --call` + tuning flags |
| `eval/` | eval set | CER/WER, latency, speaker accuracy | Separate scripts, not part of the live app |

Each module is testable on its own with a small script before it is wired in.

## 5. Milestones (walking skeleton first, then the weakest link)

| # | Milestone | Done when | Est. |
|---|---|---|---|
| M0 | Environment + audio routing | Python env works; BlackHole + Multi-Output set up; level-meter script shows both inputs | 2 h |
| M1 | Walking skeleton (mic only) | Speak Armenian → HY + EN lines appear in terminal | 3 h |
| M2 | Two sources | Mic → `Me`, BlackHole → `Call` lines, in parallel | 2 h |
| M3 | Eval set + measurement | CER/WER + latency per model; decide ASR decoder and NLLB size | 4 h |
| M4 | Speaker identification | 2+ call speakers get stable labels in a scripted call | 3 h |
| M5 | Reliability | VAD tuned, long-phrase cap, queue latency under load, clear errors | 3 h |
| M6 | README, chats export, rehearsal | Real call with 2+ people works end to end; README complete | 3 h |

Commit after every working step. One change at a time.

## 6. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| NeMo is heavy / awkward to install on macOS | Lost time | ONNX CTC route (`onnx-asr`) as tested alternative; decide in M3 |
| 8 GB memory → swapping | Latency spikes | Measure RSS early; NLLB 600M if 1.3B is too heavy; int8 |
| M1 Air throttles after minutes of load | Latency grows over time | Run 10-min soak test in M5 |
| Conversational Armenian is hard (Movies WER ~61 % on ArmBench) | Visible errors live | Honest README; tune VAD so segments are whole phrases |
| Both sides speak at once → queue wait | > 5 s | Measure p95 with overlap; keep models fast |
| Short phrases ("Այո") → weak speaker embeddings | Wrong / new labels | Minimum duration for creating a new speaker; tune threshold |
| macOS Microphone permission missing | Silent zeros | Level-meter check in M0; startup check that fails loudly |
| Whisper-style hallucination | Invented text | Chosen ASR is CTC/Transducer; VAD feeds speech only |
| NLLB licence is CC-BY-NC | Not for commercial use | Acceptable for the challenge; stated in README |

## 7. How we test

- **Eval set (local only, git-ignored):** 10–20 short Armenian clips — mic recordings + recordings
  through a real call (BlackHole) — each with a hand-typed reference transcript (`eval/refs/*.txt`, committed).
- **Metrics:** CER and WER (`jiwer`, with a documented Armenian text normalisation);
  latency p50/p95/max from logs; speaker label accuracy on a scripted multi-person call.
- **TESTS.md:** checklist derived from the requirements table above, filled in as we go.

## 8. Project rules

- Fail loudly: no silent fallbacks, no swallowed exceptions, no hidden retries.
- Keep it simple: only what the brief asks; no speculative features.
- Separate modules with the inputs/outputs above; wiring only in `pipeline.py`.
- Every model/library claim gets checked against its docs; decisions go into `DECISIONS.md` with numbers.
- Small commits after each working step; if something fails 3 times, step back.
- Never commit weights, audio or keys.

## 9. Open questions

- Python environment tool (lean: `uv` with Python 3.11).
- GitHub remote for the repo.
- Exact call app for the interview (routing works for any app; confirm its speaker setting later).
