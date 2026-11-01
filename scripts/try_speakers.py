"""Standalone check for the speakers module (briefs/speakers.md): label a call-side recording and score the labels.

1. The WAV is cut by the VAD exactly as live (call side), and every phrase gets its TitaNet fingerprint. Load time,
   memory and time per phrase are printed; the fingerprints are saved to logs/speakers_<wav name>.npz (git-ignored),
   so the settings can be tried again without the model: --from-cache.
2. The true speaker of each phrase comes from a turns file, one line per turn: "0:00-0:14 A" (m:ss or h:mm:ss or
   seconds; any label). A phrase gets the label it overlaps most if that covers >= 60 % of it, else it is "mixed"
   (a speaker change inside the phrase) and is fed to the matcher but not scored.
3. Every threshold x min_new_s pair is run over the phrases in order, as live. Accuracy = phrases with the right
   label after the best one-to-one pairing of found and true speakers (extra found speakers count as wrong).
Run from the repo root:
    python -m scripts.try_speakers eval/audio/spk_two.wav --turns eval/speakers/spk_two.txt
    python -m scripts.try_speakers eval/audio/spk_two.wav --turns eval/speakers/spk_two.txt --from-cache --show 0.5 1.0
"""
import argparse
import itertools
import re
import resource
import statistics
import sys
import time
import wave
from collections import Counter
from pathlib import Path

import numpy as np

from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_CALL, AudioChunk
from transcriber.speakers import SpeakerMatcher
from transcriber.vad import CHUNK_SECONDS, Segmenter

LOG_DIR = Path("logs")
MIN_SHARE = 0.6          # a phrase belongs to one speaker if that speaker covers this share of it
THRESHOLDS = [round(0.30 + 0.05 * i, 2) for i in range(11)]      # 0.30 ... 0.80
MIN_NEW_S = [0.5, 1.0, 1.5, 2.0, 3.0]


def read_wav(path: Path) -> np.ndarray:
    """Same reader as scripts/try_asr.py."""
    with wave.open(str(path)) as wav:
        found = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth() * 8)
        if found != (SAMPLE_RATE, 1, 16):
            raise SystemExit(f"error: {path} is {found[0]} Hz, {found[1]} channel(s), {found[2]}-bit; need "
                             f"{SAMPLE_RATE} Hz mono 16-bit (scripts/record.py writes that)")
        return np.frombuffer(wav.readframes(wav.getnframes()), "<i2").astype(np.float32) / 32768


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS, KiB on Linux
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def seconds_of(text: str) -> float:
    parts = [float(p) for p in text.split(":")]
    if not 1 <= len(parts) <= 3:
        raise ValueError(text)
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


def read_turns(path: Path) -> list[tuple[float, float, str]]:
    turns = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\d:.]+)\s*-\s*([\d:.]+)\s+(\S+)", line)
        try:
            start, end, label = seconds_of(match[1]), seconds_of(match[2]), match[3]
        except (TypeError, ValueError):
            raise SystemExit(f"error: {path} line {number}: expected like '0:00-0:14 A', got {line!r}")
        if end <= start:
            raise SystemExit(f"error: {path} line {number}: the turn ends before it starts")
        turns.append((start, end, label))
    if not turns:
        raise SystemExit(f"error: no turns in {path}: it has only comments. Add one line per turn of the "
                         f"recording, like '0:00-0:14 A' (who speaks from when to when).")
    return turns


def true_label(start: float, end: float, turns) -> str | None:
    """The speaker covering >= MIN_SHARE of the phrase, else None (mixed or not in any turn)."""
    overlap = Counter()
    for t_start, t_end, label in turns:
        overlap[label] += max(0.0, min(end, t_end) - max(start, t_start))
    if not overlap:
        return None
    label, covered = overlap.most_common(1)[0]
    return label if covered >= MIN_SHARE * (end - start) else None


def accuracy(predicted: list[int], truth: list[str | None]) -> tuple[int, int]:
    """(right, scored) after the best one-to-one pairing of predicted speakers with true ones."""
    pairs = [(p, t) for p, t in zip(predicted, truth) if t is not None]
    counts = Counter(pairs)
    found, real = sorted({p for p, _ in pairs}), sorted({t for _, t in pairs})
    if len(found) >= len(real):
        best = max(sum(counts[(p, t)] for t, p in zip(real, perm)) for perm in itertools.permutations(found, len(real)))
    else:
        best = max(sum(counts[(p, t)] for p, t in zip(found, perm)) for perm in itertools.permutations(real, len(found)))
    return best, len(pairs)


def run_matcher(embeddings, lengths, threshold, min_new_s) -> tuple[list[int], list[float | None]]:
    matcher = SpeakerMatcher(threshold=threshold, min_new_s=min_new_s)
    labels, similarities = [], []
    for embedding, seconds in zip(embeddings, lengths):
        labels.append(matcher.match(embedding, seconds))
        similarities.append(matcher.last_similarity)
    return labels, similarities


def compute(wav: Path, cache: Path, threads: int) -> None:
    audio = read_wav(wav)
    segmenter = Segmenter(SOURCE_CALL)
    segments = []
    for i in range(len(audio) // CHUNK_SAMPLES):
        segments += segmenter.feed(AudioChunk(SOURCE_CALL, i * CHUNK_SECONDS,
                                              audio[i * CHUNK_SAMPLES:(i + 1) * CHUNK_SAMPLES]))
    segments += segmenter.flush()
    print(f"{wav}: {len(audio) / SAMPLE_RATE:.1f} s, {len(segments)} VAD phrases")

    import torch
    torch.set_num_threads(threads)      # as in the program, where Transcriber sets it (briefs/asr.md question 1)
    before, started = peak_rss_mb(), time.perf_counter()
    from transcriber.speakers import SpeakerIdentifier
    identifier = SpeakerIdentifier()
    print(f"TitaNet loaded in {time.perf_counter() - started:.1f} s (incl. imports and warm-up), "
          f"peak RSS +{peak_rss_mb() - before:.0f} MB (torch and NeMo included when loaded alone), {threads} threads")
    embeddings, took = [], []
    for segment in segments:
        t0 = time.perf_counter()
        embeddings.append(identifier.embed(segment.audio))
        took.append(time.perf_counter() - t0)
    lengths = [s.end - s.start for s in segments]
    longest = int(np.argmax(lengths))
    print(f"fingerprint per phrase: median {statistics.median(took):.3f} s, max {max(took):.3f} s "
          f"(longest phrase {lengths[longest]:.1f} s: {took[longest]:.3f} s); peak RSS {peak_rss_mb():.0f} MB")
    LOG_DIR.mkdir(exist_ok=True)
    np.savez(cache, starts=np.array([s.start for s in segments]), ends=np.array([s.end for s in segments]),
             embeddings=np.stack(embeddings), seconds=np.array(took))
    print(f"saved {cache}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("wav", type=Path, help="call-side recording, 16 kHz mono 16-bit")
    parser.add_argument("--turns", type=Path, required=True, help="who spoke when, one line per turn: 0:00-0:14 A")
    parser.add_argument("--from-cache", action="store_true", help="use the saved fingerprints, do not load TitaNet")
    parser.add_argument("--threads", type=int, default=4, help="torch CPU threads (the program uses 4)")
    parser.add_argument("--thresholds", type=float, nargs="+", default=THRESHOLDS)
    parser.add_argument("--min-new-s", type=float, nargs="+", default=MIN_NEW_S)
    parser.add_argument("--show", type=float, nargs=2, metavar=("THRESHOLD", "MIN_NEW_S"),
                        help="print every phrase for this setting")
    args = parser.parse_args()
    turns = read_turns(args.turns)
    cache = LOG_DIR / f"speakers_{args.wav.stem}.npz"
    if not args.from_cache:
        if not args.wav.is_file():
            raise SystemExit(f"error: {args.wav} not found")
        compute(args.wav, cache, args.threads)
    elif not cache.is_file():
        raise SystemExit(f"error: no saved fingerprints {cache}; run once without --from-cache")
    data = np.load(cache)
    starts, ends, embeddings = data["starts"], data["ends"], data["embeddings"]
    lengths = list(ends - starts)
    truth = [true_label(s, e, turns) for s, e in zip(starts, ends)]
    real = sorted({t for t in truth if t})
    print(f"\n{len(truth)} phrases: {sum(t is not None for t in truth)} scored, {truth.count(None)} mixed or outside "
          f"the turns; true speakers: {', '.join(f'{r} ({truth.count(r)})' for r in real)}")

    pairwise = embeddings @ embeddings.T
    same = [pairwise[i, j] for i, j in itertools.combinations(range(len(truth)), 2) if truth[i] and truth[i] == truth[j]]
    other = [pairwise[i, j] for i, j in itertools.combinations(range(len(truth)), 2)
             if truth[i] and truth[j] and truth[i] != truth[j]]
    if same and other:
        print(f"similarity between two phrases: same speaker median {np.median(same):.2f} (5th pct "
              f"{np.percentile(same, 5):.2f}), different speakers median {np.median(other):.2f} "
              f"(95th pct {np.percentile(other, 95):.2f})")

    print(f"\naccuracy (speakers found) per threshold (rows) and min_new_s (columns):")
    print("         " + "".join(f"{m:>14g} s" for m in args.min_new_s))
    for threshold in args.thresholds:
        cells = []
        for min_new_s in args.min_new_s:
            labels, _ = run_matcher(embeddings, lengths, threshold, min_new_s)
            right, scored = accuracy(labels, truth)
            cells.append(f"{right / scored:7.0%} ({len(set(labels))})")
        print(f"  {threshold:5.2f}  " + "".join(f"{c:>16}" for c in cells))

    if args.show:
        threshold, min_new_s = args.show
        labels, similarities = run_matcher(embeddings, lengths, threshold, min_new_s)
        print(f"\nthreshold {threshold:g}, min_new_s {min_new_s:g}:  start-end  length  true  found  similarity")
        for s, e, t, p, sim in zip(starts, ends, truth, labels, similarities):
            print(f"  {s:7.2f}-{e:7.2f}  {e - s:5.2f}s  {t or 'mixed':>5}  Speaker {p + 1}  "
                  f"{'-' if sim is None else f'{sim:.2f}'}")


if __name__ == "__main__":
    main()
