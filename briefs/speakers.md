# Brief — speakers

**Goal:** label call-side segments `Speaker 1`, `Speaker 2`, …, with the same person keeping the same
label for the whole session (R5). Settle D4: SpeechBrain ECAPA vs NVIDIA TitaNet.

**Read:** `MODULES.md`, `transcriber/contracts.py`, `transcriber/speakers.py`, `DECISIONS.md` D0, D1a, D4.

**May edit:** `transcriber/speakers.py`, `scripts/try_speakers.py`, `tests/test_speakers.py`,
`eval/speakers/*.csv`, `requirements.txt` (append), `DECISIONS.md` (D4), `TESTS.md` (speakers section), this brief.

## Contract (signature in `transcriber/speakers.py`)
- `SpeakerIdentifier(**tuning)`, `identify(audio) -> str` always returns `"Speaker N"`, with N counted in
  order of first appearance. Never `"Me"`. One instance per session, called from one thread.
- Short segments (e.g. "Այո") give weak embeddings. What happens to them must be decided and written in
  Status. For example: join the closest known speaker, never create a new one.

## Method (from D4)
One embedding per segment, then cosine similarity to each speaker's centroid. The best match above the
threshold joins that speaker and updates the centroid. Otherwise a new speaker is created, but only if the
segment is long enough. Keep the matching logic separate from the embedding model, so
`tests/test_speakers.py` can test it with made-up vectors. D1a chose NeMo, so TitaNet adds no new library;
compare memory either way. Torch's thread count is process-wide and set by `Transcriber` (briefs/asr.md
contract question 1).

## Test data
Play an Armenian interview or podcast with 2–3 known voices to "Call Output" and record BlackHole with
`scripts/record.py`. Cut it into segments with `scripts/try_vad.py` and label the true speaker of each in
`eval/speakers/interview1.csv` (`file,true_speaker`).

## Standalone check
```
python -m scripts.try_speakers eval/speakers/interview1.csv
```
For each segment it prints the predicted vs the true speaker. Then it prints the accuracy after the best
mapping of labels, the number of speakers found, and the time per segment.

## Done when
- [ ] 2-voice and 3-voice recordings: speaker count and accuracy measured (honest numbers)
- [ ] threshold and minimum new-speaker length chosen by measuring and written into D4
- [ ] time per segment and RSS in Status (targets: ≤ 0.3 s, ≤ 0.3 GB)

**Out of scope:** names, remembering speakers across sessions, overlapping speech (write it down as a limitation).

## Status
(not started)

## Contract questions
(none)
