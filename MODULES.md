# MODULES — how the project is split

Each module is built and tested **in its own chat**, against a fixed contract, and is wired
into the program (`transcriber/pipeline.py`) only after its own checks pass (Tip 3).

## Map

```
Mic ───────► audio ─► vad ──────────────── "Me" ─┐
                                                 ├─► queue ─► asr ─► mt ─► output
BlackHole ─► audio ─► vad ─► speakers ───────────┘
            (pipeline.py wires everything; main.py is the CLI)
```

| Module | File | In | Out | Brief | Decision |
|---|---|---|---|---|---|
| audio | `transcriber/audio.py` | device name or id | `AudioChunk`s (32 ms, 16 kHz mono) on a queue | `briefs/audio.md` | — |
| vad | `transcriber/vad.py` | `AudioChunk`s of one source | `Segment` (start, end, audio) | `briefs/vad.md` | D2 |
| asr | `transcriber/asr.py` | float32 16 kHz audio | Armenian text | `briefs/asr.md` | D1a |
| mt | `transcriber/mt.py` | Armenian text | English text | `briefs/mt.md` | D3a |
| speakers | `transcriber/speakers.py` | call-side segment audio | `"Speaker N"` | `briefs/speakers.md` | D4 |
| eval | `eval/` | clips + reference texts + latency log | CER/WER, latency p50/p95/max | `briefs/eval.md` | — |
| integration | `pipeline.py`, `output.py`, `main.py`, README | CLI flags | terminal lines | `briefs/integration.md` | D5 |

**Shared contract:** `transcriber/contracts.py` — `AudioChunk`, `Segment`, `SAMPLE_RATE`, `CHUNK_SAMPLES`.
Each module file already holds its interface (signatures + docstrings, bodies raise `NotImplementedError`).

## Rules for every module chat

1. **Context:** read only `MODULES.md`, your brief, and the files your brief lists.
2. **Scope:** edit only the files your brief lists. Never edit another module, `contracts.py` or
   `pipeline.py`. If the contract looks wrong, write it under *Contract questions* in your brief
   and carry on; the integration chat decides and logs it in `DECISIONS.md`.
3. **No cross-imports:** modules in `transcriber/` import only `transcriber.contracts`.
   Scripts (`scripts/`) and `eval/` may import any module.
4. **Construction:** constructors work with their defaults (only `source`/`device`-type args are
   required), load models once, and raise if loading fails.
5. **Fail loudly:** no silent fallbacks, no swallowed exceptions, no hidden retries or timeouts.
6. **Local only:** models download once into a cache outside the repo; nothing is fetched at run time
   (check with Wi-Fi off). Never commit weights or audio.
7. **One shared `.venv`:** add your packages to `requirements.txt`. Do not upgrade or downgrade a package
   another module uses (numpy, torch, …) without writing it into `DECISIONS.md`.
8. **Run from the repo root:** `python -m scripts.try_asr` (so `import transcriber` works).
9. **Measure:** model modules report load time, memory (RSS) after load, and time per call.
10. **Verify:** check model names, APIs and parameters against their docs before using them; say the source.
11. **Finish:** tick the brief's checklist → fill in its *Status* → update the module's `DECISIONS.md`
    entry and `TESTS.md` section → user commits (message prefix = module, e.g. `asr: add Transcriber`)
    → user exports the chat to `chats/`.

## Budgets (targets to check by measuring, not facts)

| | Memory (RSS added) | Time per call |
|---|---|---|
| vad (×2, one per source) | ≤ 0.05 GB each | a few ms per chunk |
| speakers | ≤ 0.3 GB | ≤ 0.3 s per segment |
| asr | ≤ 1.0 GB | ≤ 0.8 s for a 10 s segment |
| mt | ≤ 1.5 GB | ≤ 0.8 s per segment |
| Python, torch, buffers | ≤ 0.7 GB | — |
| **Whole program** | **≤ ~3.5 GB** (8 GB Mac) | |

Latency path for one phrase: silence needed to close it (~0.6 s) + speakers + asr + mt ≈ 2.5 s,
which leaves ~2.5 s for waiting in the queue when both sides talk. Limit: 5 s.

## Shared formats

- **Latency log** `logs/latency.csv` (written by the pipeline, read by `eval/latency.py`, git-ignored),
  one row per printed segment:
  `source,speaker,seg_start,seg_end,asr_s,mt_s,printed_at`
  (`seg_*` and `printed_at` in session seconds, `*_s` = durations; latency = `printed_at − seg_end`).
- **Test audio:** `eval/audio/*.wav`, 16 kHz mono (git-ignored). **Reference text:** `eval/refs/<same name>.txt`
  (committed).

## Order

Walking skeleton first (Tip 2): the first version of each module is the simplest one that meets the
contract. Improvements come after the program runs end to end, aimed at the weakest measured link.

| Step | Chat | Gives | Milestone |
|---|---|---|---|
| 1 | audio | capture + `scripts/record.py` to record test clips | M1 prep |
| 2 | asr (biggest risk: NeMo on macOS) · mt in parallel (text only, needs no audio) | first working models | M1 prep |
| 3 | vad | phrases from a stream | M1 prep |
| 4 | integration v1 | mic only end to end, then both sources | M1, M2 |
| 5 | eval | eval set + numbers → decide D1a, D3a | M3 |
| 6 | speakers | stable call-side labels | M4 |
| 7 | integration v2 | reliability, 10-min soak test, README, rehearsal | M5, M6 |

Chats that touch different files can run at the same time in the same folder (`requirements.txt`: append only).

## Starting a module chat

Connect the `armenian-transcriber` folder, attach nothing else, and paste (example for asr):

> We are building the **asr** module of the armenian-transcriber project. Read `MODULES.md` and
> `briefs/asr.md`, then only the files the brief lists. Follow the rules in `MODULES.md`.
> Explain your plan in detail first, then write one piece at a time; I review, run and commit.

Export each chat as `chats/NN-name.md` (NN = order started, e.g. `chats/03-audio.md`).
