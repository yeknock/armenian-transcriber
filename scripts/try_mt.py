"""Standalone check for the MT module (briefs/mt.md): translate a file of Armenian lines and time it.

Prints load time and memory at start, then for each line: HY, EN, the number of pieces sent to NLLB (every sentence
must show up in the English), the number of words and the time. At the end: median / p95 / max time per line against
the latency targets. Lines starting with # are comments. Run from the repo root:
    python -m scripts.try_mt eval/mt_sentences.txt
    python -m scripts.try_mt eval/mt_sentences.txt --beam 2 --repeat 3
    python -m scripts.try_mt eval/mt_short.txt --scores            # short inputs: score per sentence
    python -m scripts.try_mt eval/mt_short.txt --scores --whole    # each line as one piece, not split
Models (see transcriber/mt.py): nllb-600m (default), nllb-1.3b. --whole is a diagnostic only: the program always
uses make_pieces (Translator.translate).
"""
import argparse
import resource
import statistics
import sys
import time
from pathlib import Path

from transcriber.mt import MODELS, Piece

# Latency targets per line (briefs/mt.md Status: replay of the 10.8 min Zoom call with MT added to the worker).
# A flat 0.5 s per phrase kept every phrase under 5 s (max 4.46 s); 0.8 s per phrase put 3 phrases over. Most
# phrases are short (median 3 words), so the median line must stay <= 0.5 s and the longest (~24 words) <= 0.8 s.
TARGET_MEDIAN_S = 0.5
TARGET_MAX_S = 0.8


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS, KiB on Linux
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def verdict(value: float, target: float) -> str:
    return f"{value:.3f} s (target <= {target} s: {'OK' if value <= target else 'OVER'})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", type=Path, help="text file, one Armenian segment per line")
    parser.add_argument("--model", choices=list(MODELS), default="nllb-600m")
    parser.add_argument("--beam", type=int, default=1, help="beam size: 1 = greedy (D3a default)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=1, help="runs per line; the median time is shown")
    parser.add_argument("--whole", action="store_true", help="translate each line as one piece (no splitting)")
    parser.add_argument("--scores", action="store_true", help="show the score of each translated piece")
    parser.add_argument("--no-repeat", type=int, default=4, metavar="N",
                        help="forbid any N output tokens from repeating (0 = off; D3c default 4)")
    parser.add_argument("--written", action="store_true",
                        help="convert spoken Armenian forms to written ones before NLLB (mt.to_written, D3d)")
    parser.add_argument("--rep-penalty", type=float, default=1.0, metavar="P",
                        help="penalty for tokens already written (1.0 = off, e.g. 1.2)")
    args = parser.parse_args()
    if args.repeat < 1:
        raise SystemExit("error: --repeat must be >= 1")
    if not args.path.is_file():
        raise SystemExit(f"error: {args.path} not found")
    lines = [line.strip() for line in args.path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    if not lines:
        raise SystemExit(f"error: no lines to translate in {args.path}")

    # transformers imports torch (~0.6 GB). In the full program NeMo has loaded torch already, so the libraries
    # and the model are measured separately: only "model" is what MT adds next to the ASR.
    start_mb = peak_rss_mb()
    started = time.perf_counter()
    import ctranslate2
    import torch  # noqa: F401  (transformers loads it lazily, on first use; load it here so it counts as a library)
    import transformers  # noqa: F401
    libs_mb = peak_rss_mb()
    from transcriber.mt import Translator
    translator = Translator(model=args.model, beam_size=args.beam, threads=args.threads,
                            no_repeat_ngram_size=args.no_repeat, repetition_penalty=args.rep_penalty,
                            spoken_to_written=args.written)
    model_mb = peak_rss_mb()
    print(f"model {args.model}, beam {args.beam}, {args.threads} thread(s), no-repeat {args.no_repeat}, "
          f"rep-penalty {args.rep_penalty}, written {args.written}, CTranslate2 {ctranslate2.__version__} "
          f"(CPU compute types: {', '.join(sorted(ctranslate2.get_supported_compute_types('cpu')))})")
    print(f"loaded in {time.perf_counter() - started:.2f} s (incl. imports and warm-up); peak RSS {model_mb:.0f} MB "
          f"= start {start_mb:.0f} + libraries {libs_mb - start_mb:.0f} (torch included) + model {model_mb - libs_mb:.0f}")

    print(f"mode: {'whole lines (no splitting, diagnostic)' if args.whole else 'pieces from make_pieces (as the program)'}")
    times, words = [], []
    for number, line in enumerate(lines, 1):
        runs = []
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            if args.whole:
                pieces = [Piece(line, en, "nllb", sc) for en, sc in translator.translate_pieces([line])]
            else:
                pieces = translator.translate_detailed(line)    # translate() = these English pieces joined
            runs.append(time.perf_counter() - t0)
        took = statistics.median(runs)
        times.append(took)
        words.append(len(line.split()))
        english = " ".join(p.en for p in pieces if p.en)
        how = " / ".join(p.how if p.score is None or not args.scores else f"{p.how} {p.score:.2f}" for p in pieces)
        changed = " ".join(p.nllb_input or p.hy for p in pieces)
        nllb_got = f"\n    NLLB got: {changed}" if any(p.nllb_input for p in pieces) else ""
        print(f"\n{number:2d}. HY: {line}{nllb_got}\n    EN: {english if english else '(empty)'}\n"
              f"    {len(pieces)} piece{'s' if len(pieces) != 1 else ''} ({how}), {words[-1]} words, {took:.3f} s")

    longest = max(range(len(lines)), key=lambda i: words[i])
    p95 = sorted(times)[min(len(times) - 1, int(0.95 * len(times)))]
    print(f"\n{len(lines)} lines, beam {args.beam}: median {verdict(statistics.median(times), TARGET_MEDIAN_S)}, "
          f"p95 {p95:.3f} s, max {verdict(max(times), TARGET_MAX_S)}")
    print(f"longest line: #{longest + 1}, {words[longest]} words, {times[longest]:.3f} s; "
          f"peak RSS {peak_rss_mb():.0f} MB")


if __name__ == "__main__":
    main()
