# Handover 02 — module split (2026-10-24, handover written 2026-11-01)

> Summary of session 2 for the next chat (goal, what was built, decisions, open items).
> This is **not** the chat export. The full, unedited transcript of this session is `chats/02-module-split.md`.

## Goal
- Start of session: re-read the brief (`Mathrix_AI_Coding_Challenge.docx`), the tips (`Mathrix_AI_Vibe_Coding_Tips.docx`),
  `chats/handover-01.md`, `PLAN.md`, `DECISIONS.md`, and find out which stage the project is at.
- Main task (user's request, Tip 3): split the project into modules with clear inputs and outputs, so that each one can be
  built and tested in its own chat and is merged into the main program only after its own checks pass.

## Checked at the start
- Stage: M0 almost done. The user confirmed the level-meter test works → R1 ✅, M0 ✅.
- `PLAN.md` §2 and `DECISIONS.md` D0 said "wired headphones", but `handover-01.md` says development uses the MacBook mic and
  speakers (earbuds set aside) → fixed in both files.
- `PLAN.md` §9 still listed "uv with Python 3.11" and "GitHub remote" as open, but both were settled in D0a → removed.
- Git: `.DS_Store` was tracked although ignored, and the deletion of the empty test file `file` was not committed → the user
  ran `git rm --cached .DS_Store` and `git rm file`.
- `TESTS.md` did not exist (Tip 4) → created.
- What this session can do: the shell on the Mac is a Linux sandbox with the project folder mounted. It can read and write
  files and look at git, but it cannot run the macOS `.venv` Python, reach audio devices, or commit safely (file deletion is
  off, so git leaves lock files). The user runs Python and git.

## Decisions (proposed by Claude, accepted and committed by the user)
| Question | Choice | Why |
|---|---|---|
| Module split | 7 modules: audio, vad, asr, mt, speakers, eval, integration | Each has one input and one output; each is testable alone with WAV files or text |
| Layout | Flat package `transcriber/`, one file per module | Sub-packages (earlier PLAN §4 draft) = more files, no benefit at this size |
| Shared types file | `transcriber/contracts.py`, not `types.py` | A file named `types.py` hides Python's built-in `types` module when a script runs from inside the package |
| Contract in code | Each module file holds its signatures + docstrings, bodies raise `NotImplementedError` | Chats build against a fixed interface |
| Imports | Modules import only `transcriber.contracts`; only `pipeline.py` wires them | No hidden coupling between chats |
| VAD style | Push-based `Segmenter.feed()`: no threads, queues or clock reads | A WAV file behaves exactly like live audio |
| Threads | Only `AudioCapture` may own a thread | Threading stays in audio + pipeline |
| Git | No branch per module; each chat commits only its own files, message prefix = module | All chats share one working folder; switching branches would change files under another chat |
| Order | audio → asr (mt in parallel) → vad → integration v1 (M1, M2) → eval (M3) → speakers (M4) → integration v2 (M5, M6) | Walking skeleton first (Tip 2); audio first because it gives the recorder for test clips; asr is the biggest install risk |
| Per-chat context | One brief per module in `briefs/`, with a Status section at the end | Tip 6: little but the right context |

Full record: `DECISIONS.md` D6.

## What was built
1. `transcriber/contracts.py`: `SAMPLE_RATE = 16000`, `CHUNK_SAMPLES = 512` (Silero takes 512 samples at 16 kHz),
   `SOURCE_MIC = "mic"`, `SOURCE_CALL = "call"`, frozen `AudioChunk(source, start, samples)`, and
   `Segment(source, start, end, audio, speaker, hy_text, en_text)`. Latency clock starts at `Segment.end`.
2. Interface stubs:
   - `audio.py`: `list_input_devices()`, `resolve_device(spec)`, `AudioCapture(source, device, session_start, out)` with
     `start / stop / dropouts / peak`
   - `vad.py`: `Segmenter(source)` with `feed / flush / dropped_short`
   - `asr.py`: `Transcriber().transcribe(audio) -> str`
   - `mt.py`: `Translator().translate(hy_text) -> str`
   - `speakers.py`: `SpeakerIdentifier().identify(audio) -> "Speaker N"`
   - `pipeline.py`, `output.py`, `main.py`: not created, left to the integration chat.
3. `MODULES.md`: module map and table; 11 rules for every module chat (read and edit only what the brief lists, fail
   loudly, local only, one shared `.venv` with no version changes to shared packages unless logged, run as
   `python -m scripts.try_x` from the repo root, measure load time, RSS and time per call, verify APIs in the docs);
   memory and latency budgets (targets, not facts; whole program ≤ ~3.5 GB, ~2.5 s per phrase leaving ~2.5 s of queue
   headroom); shared formats (`logs/latency.csv` columns `source,speaker,seg_start,seg_end,asr_s,mt_s,printed_at`;
   `eval/audio/*.wav` git-ignored, `eval/refs/*.txt` committed); build order; the first message to paste into a module
   chat; export naming `chats/NN-name.md`.
4. `briefs/`: `audio.md`, `vad.md`, `asr.md`, `mt.md`, `speakers.md`, `eval.md`, `integration.md`. Each has: goal, files to
   read, files it may edit, contract, what to verify first, standalone check command, "done when" list, out of scope,
   Status, Contract questions.
5. `TESTS.md`: requirement checks R1–R8 (R2a–c, R5a–c, R7a–b) and edge cases E1–E6, taken from the brief, not from code.
   Module chats add their own sections.
6. Doc updates: `PLAN.md` (§2 audio line, §4 now points to MODULES.md, M0 ✅, Core data object → `contracts.py`, §9 open
   questions: call app, speakers vs headphones); `DECISIONS.md` (D0 fixed, D6 added); `.gitignore` (`logs/`).
7. `chats/02-module-split.md`: made by a script from this session's transcript file. Only the app's `<system-reminder>`
   blocks and the model's hidden reasoning were removed.

Commits: `7dc2a33` (module split), `c2d9a30` (session 2 export).

## Changes along the way
- The shared types file was first written as `types.py`, then renamed to `contracts.py` before commit (stdlib clash).
- A `transcriber/__pycache__/` folder from the syntax check could not be deleted from the sandbox; git ignores it.

## Notes for other chats
- The budgets in `MODULES.md` are targets to check by measuring. The VAD chat has since measured 0.32 s for closing a
  phrase, against the ~0.6 s assumed there.
- Contract changes go into the brief's *Contract questions*; only the integration chat edits `contracts.py` or
  `pipeline.py`, and logs the change in `DECISIONS.md`.
- User preferences from `handover-01.md` still apply: explain first, then one piece at a time; explain the cause of a
  failure before fixing it; no `< >` placeholders and no `#` comments in commands meant for zsh.

## Still open
- Session 1 export is still missing from `chats/` (`handover-01.md` is only a summary).
- `chats/02-module-split.md` ends at the export step. It does not include the last reply of 2026-10-24 or this handover
  request of 2026-11-01; those are only in the original chat in the app.
- A project rules file (`CLAUDE.md`) was suggested but not made; the rules live in `MODULES.md`.
