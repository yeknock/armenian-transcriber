"""ASR evaluation on recordings with a correct reference text (briefs/eval.md): CER / WER, per file and in total.

Each WAV goes the same way as audio in a live call (scripts/live_asr.py): fed to the VAD in 32 ms chunks, every
phrase it cuts is transcribed, phrases the live script would hide as non-speech (mt.is_non_speech) are dropped, and
the phrases are joined in order. That text is scored against <refs>/<same name>.txt after normalisation
(eval/metrics.py). So the numbers include VAD cuts, as live, not only the ASR model. Run from the repo root:
    python -m eval.run_asr eval/audio/real --refs eval/real
    python -m eval.run_asr eval/audio/real --refs eval/real --align      # word-by-word errors
    python -m eval.run_asr eval/audio/real --refs eval/real --beam 4     # RNNT beam search instead of greedy
    python -m eval.run_asr eval/audio/real --refs eval/real --soft-max-s 8 --max-segment-s 15   # longer phrases
    python -m eval.run_asr eval/audio/real --refs eval/real --min-dip-ms 96 160 224 --segments  # 3 VAD settings
Defaults are the program's settings (greedy, VAD early cut after 5 s at a 96 ms dip, hard cut at 10 s: D1a, D2).
Several --min-dip-ms values run one after the other with one model load, followed by a summary table.
--segments prints every phrase: its times, how long after its end the VAD handed it over (about 0.06 s = early cut
at a dip, 0.32 s = a pause, other values = a hard cut at the quietest point; '-' = the file ended) and its text.
Input: 16 kHz mono 16-bit WAV (convert with: ffmpeg -i in.mp3 -ar 16000 -ac 1 -sample_fmt s16 out.wav).
A report is also written to logs/eval_asr_<time>.txt (git-ignored), to compare settings later.
"""
import argparse
import statistics
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from eval.metrics import cer, normalize, wer, word_alignment
from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_MIC, AudioChunk
from transcriber.mt import is_non_speech
from transcriber.vad import CHUNK_SECONDS, Segmenter

LOG_DIR = Path("logs")


def read_wav(path: Path) -> np.ndarray:
    """Same reader as scripts/try_asr.py."""
    with wave.open(str(path)) as wav:
        found = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth() * 8)
        if found != (SAMPLE_RATE, 1, 16):
            raise SystemExit(f"error: {path} is {found[0]} Hz, {found[1]} channel(s), {found[2]}-bit; need "
                             f"{SAMPLE_RATE} Hz mono 16-bit:\n  ffmpeg -i <original> -ar {SAMPLE_RATE} -ac 1 "
                             f"-sample_fmt s16 {path}")
        return np.frombuffer(wav.readframes(wav.getnframes()), "<i2").astype(np.float32) / 32768


def segments_of(audio: np.ndarray, vad_tuning: dict) -> list[tuple]:
    """The VAD's phrases, exactly as live: one Segmenter, chunk by chunk, flush at the end.
    Returns (segment, hand-over delay in s after segment.end, or None when flush() returned it at the end of the file)."""
    segmenter = Segmenter(SOURCE_MIC, **vad_tuning)   # the label does not change how audio is cut
    found = []
    for i in range(len(audio) // CHUNK_SAMPLES):
        chunk = AudioChunk(SOURCE_MIC, i * CHUNK_SECONDS, audio[i * CHUNK_SAMPLES:(i + 1) * CHUNK_SAMPLES])
        found += [(s, chunk.start + CHUNK_SECONDS - s.end) for s in segmenter.feed(chunk)]
    return found + [(s, None) for s in segmenter.flush()]


def evaluate(files, audios, references, transcriber, vad_tuning: dict, align: bool, show_segments: bool) -> tuple:
    """Run every clip with one VAD setting. Returns (report lines, summary row)."""
    report, hypotheses, asr_times, delays, count = [], {}, [], [], 0
    for path in files:
        audio = audios[path]
        texts, skipped, took, phrase_lines = [], 0, [], []
        for segment, delay in segments_of(audio, vad_tuning):
            t0 = time.perf_counter()
            text = transcriber.transcribe(segment.audio)
            took.append(time.perf_counter() - t0)
            if delay is not None:
                delays.append(delay)
            hidden = not text or is_non_speech(text)
            skipped += hidden
            if not hidden:
                texts.append(text)
            phrase_lines.append(f"    {segment.start:6.2f}-{segment.end:6.2f} s  "
                                f"{'-' if delay is None else f'{delay:.2f}':>5}  "
                                f"{'(non-speech, dropped) ' if hidden else ''}{text}")
        count += len(took)
        asr_times += took
        hypotheses[path] = " ".join(texts)
        ref, hyp = references[path], hypotheses[path]
        lines = [f"\n{path.name}: {len(audio) / SAMPLE_RATE:.1f} s, {len(took)} VAD segment(s)"
                 + (f" ({skipped} non-speech dropped)" if skipped else "")
                 + (f", ASR {sum(took):.2f} s (max {max(took):.2f} s per segment)" if took else ""),
                 f"  CER {cer([ref], [hyp]):.1%}   WER {wer([ref], [hyp]):.1%}   "
                 f"({len(normalize(ref).split())} reference words, {len(normalize(hyp).split())} recognised)",
                 f"  REF: {ref}",
                 f"  ASR: {hyp if hyp else '(nothing)'}"]
        if show_segments:
            lines += ["  phrases (start-end, handed over after, text):"] + phrase_lines
        if align:
            lines.append(word_alignment(ref, hyp).rstrip())
        print("\n".join(lines), flush=True)
        report += lines
    refs, hyps = [references[p] for p in files], [hypotheses[p] for p in files]
    row = {"cer": cer(refs, hyps), "wer": wer(refs, hyps), "segments": count,
           "delay_p50": statistics.median(delays) if delays else float("nan"),
           "delay_max": max(delays) if delays else float("nan"),
           "asr_p50": statistics.median(asr_times) if asr_times else float("nan"),
           "asr_max": max(asr_times) if asr_times else float("nan")}
    total = (f"\nTOTAL {len(files)} file(s): CER {row['cer']:.1%}   WER {row['wer']:.1%}   "
             f"{count} phrases, handed over p50 {row['delay_p50']:.2f} s / max {row['delay_max']:.2f} s   "
             f"ASR per segment median {row['asr_p50']:.2f} s, max {row['asr_max']:.2f} s")
    print(total, flush=True)
    return report + [total], row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="WAV files or folders of WAVs")
    parser.add_argument("--refs", type=Path, required=True, help="folder with <wav name>.txt reference texts")
    parser.add_argument("--threads", type=int, default=4, help="CPU threads for the ASR model")
    parser.add_argument("--align", action="store_true", help="also print the word-by-word alignment per file")
    parser.add_argument("--beam", type=int, default=1, help="ASR beam size: 1 = greedy (default), > 1 = beam search")
    parser.add_argument("--soft-max-s", type=float, default=5.0,
                        help="VAD: after this many seconds, the first short dip ends a phrase (default 5)")
    parser.add_argument("--max-segment-s", type=float, default=10.0,
                        help="VAD: a phrase is cut at its quietest point at this length (default 10; ASR takes <= 20)")
    parser.add_argument("--min-dip-ms", type=float, nargs="+", default=[96.0],
                        help="VAD: length of the dip that ends a phrase after --soft-max-s (default 96); "
                             "several values = several runs with one model load")
    parser.add_argument("--segments", action="store_true", help="print every phrase with its times and text")
    args = parser.parse_args()
    tunings = [{"soft_max_s": args.soft_max_s, "max_segment_s": args.max_segment_s, "min_dip_ms": dip}
               for dip in args.min_dip_ms]
    try:
        for tuning in tunings:
            Segmenter(SOURCE_MIC, **tuning)    # bad settings fail here, before the slow model load
    except ValueError as error:
        raise SystemExit(f"error: {error}")

    files = []
    for path in args.paths:
        found = sorted(path.glob("*.wav")) if path.is_dir() else [path] if path.is_file() else None
        if not found:
            raise SystemExit(f"error: no WAV file at {path}")
        files += found
    references = {}
    for path in files:                         # every reference must exist before the slow model load
        ref_path = args.refs / f"{path.stem}.txt"
        if not ref_path.is_file():
            raise SystemExit(f"error: no reference text {ref_path} for {path}")
        references[path] = ref_path.read_text(encoding="utf-8").strip()
        if not normalize(references[path]):
            raise SystemExit(f"error: {ref_path} has no words")
    audios = {path: read_wav(path) for path in files}

    started = time.perf_counter()
    from transcriber.asr import Transcriber    # imported here so its import time counts as load time
    transcriber = Transcriber(threads=args.threads, beam_size=args.beam)
    report = [f"eval.run_asr {datetime.now():%Y-%m-%d %H:%M}: {len(files)} file(s), refs {args.refs}, "
              f"ASR beam {transcriber.beam_size} ({'greedy' if transcriber.beam_size == 1 else 'malsd_batch'}), "
              f"threads {transcriber.threads}, loaded in {time.perf_counter() - started:.1f} s"]
    print(report[0], flush=True)

    rows = []
    for tuning in tunings:
        heading = (f"\n===== VAD: early cut after {tuning['soft_max_s']:g} s at a {tuning['min_dip_ms']:g} ms dip, "
                   f"hard cut at {tuning['max_segment_s']:g} s")
        print(heading, flush=True)
        lines, row = evaluate(files, audios, references, transcriber, tuning, args.align, args.segments)
        report += [heading] + lines
        rows.append((tuning, row))
    if len(rows) > 1:
        words = sum(len(normalize(references[p]).split()) for p in files)
        summary = [f"\nSUMMARY (one word = {1 / words:.1%} of WER on {words} reference words)",
                   "  min dip   CER     WER    phrases  hand-over p50 / max   ASR p50 / max"]
        summary += [f"  {t['min_dip_ms']:5g} ms  {r['cer']:5.1%}  {r['wer']:5.1%}  {r['segments']:7d}  "
                    f"{r['delay_p50']:9.2f} / {r['delay_max']:.2f} s   {r['asr_p50']:.2f} / {r['asr_max']:.2f} s"
                    for t, r in rows]
        print("\n".join(summary))
        report += summary

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"eval_asr_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"report: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
