"""Does the VAD's way of cutting change the English? Same recording, two VAD settings, the program's ASR and MT.

Runs a WAV through VAD -> ASR -> MT exactly as the live program does (non-speech dropped), once per setting, and
prints each setting's phrases with their times, Armenian and English, then the whole English text of each setting
one after the other, so a person can judge which reads better. Settings are "soft_max_s/max_segment_s":
5/10 is the program's (D2); 8/15 cuts long speech less often (tried and reverted 2026-11-01). Run from the repo root:
    python -m eval.compare_vad_mt eval/audio/spk_two.wav
    python -m eval.compare_vad_mt eval/audio/spk_two.wav --settings 5/10 8/15 --mt-model nllb-1.3b
A report is also written to logs/vad_mt_<wav name>.txt (git-ignored: real speech).
"""
import argparse
import statistics
import time
from pathlib import Path

from eval.run_asr import read_wav, segments_of
from transcriber.mt import MODELS, is_non_speech
from transcriber.vad import Segmenter
from transcriber.contracts import SOURCE_MIC


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("wav", type=Path, help="16 kHz mono 16-bit WAV")
    parser.add_argument("--settings", nargs="+", default=["5/10", "8/15"], help="soft_max_s/max_segment_s pairs")
    parser.add_argument("--mt-model", choices=list(MODELS), default="nllb-1.3b")
    args = parser.parse_args()
    tunings = []
    for setting in args.settings:
        try:
            soft, hard = (float(x) for x in setting.split("/"))
            Segmenter(SOURCE_MIC, soft_max_s=soft, max_segment_s=hard)     # bad settings fail before the models load
        except ValueError as error:
            raise SystemExit(f"error: setting {setting!r}: {error}")
        tunings.append((setting, {"soft_max_s": soft, "max_segment_s": hard}))
    audio = read_wav(args.wav)

    from transcriber.asr import Transcriber
    from transcriber.mt import Translator
    transcriber, translator = Transcriber(), Translator(model=args.mt_model)
    report, whole = [f"{args.wav}: {len(audio) / 16000:.0f} s, MT {args.mt_model}"], {}
    for setting, tuning in tunings:
        lines, english, mt_times = [f"\n===== VAD {setting} (early cut after {tuning['soft_max_s']:g} s, hard cut at "
                                    f"{tuning['max_segment_s']:g} s)"], [], []
        for segment, delay in segments_of(audio, tuning):
            hy = transcriber.transcribe(segment.audio)
            if not hy or is_non_speech(hy):
                continue
            t0 = time.perf_counter()
            en = translator.translate(hy)
            mt_times.append(time.perf_counter() - t0)
            english.append(en)
            # how the phrase ended (approximate): an early cut at a dip is handed over at once (~0.06 s); a hard
            # cut only happens within 1 s of the maximum length; otherwise it ended at a pause
            length = segment.end - segment.start
            cut = ("file end" if delay is None else "early cut" if delay < 0.1 else
                   "hard cut" if length >= tuning["max_segment_s"] - 1.05 else "pause")
            lines += [f"\n[{segment.start:6.1f}-{segment.end:6.1f} s, {segment.end - segment.start:4.1f} s, {cut}]",
                      f"  HY: {hy}", f"  EN: {en}"]
        lines.append(f"\n{len(english)} phrases; MT per phrase median {statistics.median(mt_times):.2f} s, "
                     f"max {max(mt_times):.2f} s")
        whole[setting] = " ".join(english)
        print("\n".join(lines), flush=True)
        report += lines
    report.append("\n===== The whole English text per setting (read one after the other)")
    for setting, text in whole.items():
        report += [f"\n--- VAD {setting}:", text]
    print("\n".join(report[-2 * len(whole) - 1:]))
    out = Path("logs") / f"vad_mt_{args.wav.stem}.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"\nreport: {out}")


if __name__ == "__main__":
    main()
