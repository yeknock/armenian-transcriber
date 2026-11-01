"""Standalone check for the MT module (briefs/mt.md): translate a file of Armenian lines and time it.

Prints load time and peak memory at start, then for each line: HY, EN, the number of sentences found in it
(each must show up in the English) and the time. Lines starting with # are comments. Run from the repo root:
    python -m scripts.try_mt eval/mt_sentences.txt
    python -m scripts.try_mt eval/mt_sentences.txt --model nllb-1.3b --beam 4 --repeat 3
Models (see transcriber/mt.py): nllb-600m (default), nllb-1.3b.
"""
import argparse
import resource
import statistics
import sys
import time
from pathlib import Path

from transcriber.mt import MODELS, split_sentences


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS, KiB on Linux
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", type=Path, help="text file, one Armenian segment per line")
    parser.add_argument("--model", choices=list(MODELS), default="nllb-600m")
    parser.add_argument("--beam", type=int, default=2, help="beam size: 1 = greedy (fastest)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=1, help="runs per line; the median time is shown")
    args = parser.parse_args()
    if args.repeat < 1:
        raise SystemExit("error: --repeat must be >= 1")
    if not args.path.is_file():
        raise SystemExit(f"error: {args.path} not found")
    lines = [line.strip() for line in args.path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    if not lines:
        raise SystemExit(f"error: no lines to translate in {args.path}")

    before = peak_rss_mb()
    started = time.perf_counter()
    from transcriber.mt import Translator   # imported here so its import time counts as load time
    translator = Translator(model=args.model, beam_size=args.beam, threads=args.threads)
    after = peak_rss_mb()
    print(f"model {args.model}, beam {args.beam}, {args.threads} thread(s): loaded in "
          f"{time.perf_counter() - started:.2f} s (incl. imports and warm-up); peak RSS {after:.0f} MB "
          f"(+{after - before:.0f} MB for MT)")

    times = []
    for number, line in enumerate(lines, 1):
        runs = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            english = translator.translate(line)
            runs.append(time.perf_counter() - t0)
        took = statistics.median(runs)
        times.append(took)
        count = len(split_sentences(line))
        print(f"\n{number:2d}. HY: {line}\n    EN: {english if english else '(empty)'}\n"
              f"    {count} sentence{'s' if count > 1 else ''}, {took:.3f} s")

    print(f"\n{len(lines)} lines: median {statistics.median(times):.3f} s, max {max(times):.3f} s per line; "
          f"peak RSS {peak_rss_mb():.0f} MB")


if __name__ == "__main__":
    main()
