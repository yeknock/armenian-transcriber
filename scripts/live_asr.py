"""Live check of audio -> VAD -> ASR -> MT on a real call (Zoom or any other app), before the full program exists.

Prints every phrase as it is recognised: session time, side (Me = microphone, Call = BlackHole), the Armenian
text, the English, and how long after the end of the phrase it was printed (split into VAD wait, queue wait, ASR
and MT time). The ASR's text for coughs / "hmm" / breaths (mt.is_non_speech) is not printed, only counted (D3b).
Not here yet: Speaker 1/2 labels (speakers module); the full program is the integration step (pipeline.py,
main.py). Run from the repo root:
    python -m scripts.live_asr --list
    python -m scripts.live_asr --mic "MacBook Air Microphone" --call BlackHole
    python -m scripts.live_asr --mic "MacBook Air Microphone" --call BlackHole --save
Ctrl+C stops: the devices close, the last phrase is still cut, transcribed and printed, then a latency summary.
A second Ctrl+C aborts at once. Every phrase also gets a row in logs/live_asr_<time>.csv (git-ignored);
--save also keeps each phrase as WAV + text in logs/live_asr_<time>/ (only with everyone's consent).
"""
import argparse
import csv
import queue
import signal
import statistics
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from transcriber.asr import Transcriber
from transcriber.audio import AudioCapture, list_input_devices, resolve_device
from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_CALL, SOURCE_MIC
from transcriber.mt import Translator, is_non_speech
from transcriber.vad import Segmenter

LIMIT_S = 5.0                 # the brief: at most 5 s from the end of a phrase to its line
MIC_SILENCE_CHECK_S = 3.0     # the mic giving only exact zeros this long = missing macOS permission
CALL_SILENCE_WARN_S = 10.0    # BlackHole giving only exact zeros this long = the call app plays somewhere else
LABELS = {SOURCE_MIC: "Me", SOURCE_CALL: "Call"}
LOG_DIR = Path("logs")
CSV_FIELDS = ["source", "label", "seg_start", "seg_end", "handed_at", "asr_start", "asr_end", "mt_end", "printed_at",
              "latency_s", "skipped"]     # skipped = 1: non-speech, not printed (latency_s then empty)


def clock(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class AsrWorker(threading.Thread):
    """Takes (segment, handed_at) from `inbox`, transcribes, translates and prints it; None ends the thread.
    An error is kept in `error` (not swallowed): the main thread checks it and stops the program."""

    def __init__(self, transcriber: Transcriber, translator: Translator, session_start: float, csv_path: Path,
                 save_dir: Path | None) -> None:
        super().__init__(name="asr", daemon=True)
        self.inbox: queue.Queue = queue.Queue()     # unbounded: a phrase is never dropped
        self.error: Exception | None = None
        self.latencies: dict[str, list[float]] = {SOURCE_MIC: [], SOURCE_CALL: []}
        self.asr_times: list[float] = []
        self.mt_times: list[float] = []
        self.skipped: dict[str, int] = {SOURCE_MIC: 0, SOURCE_CALL: 0}
        self._transcriber = transcriber
        self._translator = translator
        self._session_start = session_start
        self._csv_path = csv_path
        self._save_dir = save_dir
        self._count = 0

    def _now(self) -> float:
        return time.monotonic() - self._session_start

    def run(self) -> None:
        try:
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                rows = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                rows.writeheader()
                while (item := self.inbox.get()) is not None:
                    rows.writerow(self._process(*item))
                    f.flush()
        except Exception as error:      # kept for the main thread, which raises it
            self.error = error

    def _process(self, segment, handed_at: float) -> dict:
        asr_start = self._now()
        text = self._transcriber.transcribe(segment.audio)
        asr_end = self._now()
        vad_s, wait_s, asr_s = handed_at - segment.end, asr_start - handed_at, asr_end - asr_start
        self.asr_times.append(asr_s)
        skipped = not text or is_non_speech(text)
        english = "" if skipped else self._translator.translate(text)
        mt_end = self._now()
        mt_s = mt_end - asr_end
        printed_at = latency = None
        if skipped:                          # a cough / "hmm" / breath: nothing to show (D3b)
            self.skipped[segment.source] += 1
        else:
            self.mt_times.append(mt_s)
            latency = mt_end - segment.end   # printing takes microseconds; measured again below
            flag = f"   OVER {LIMIT_S:g} s" if latency > LIMIT_S else ""
            print(f"\n[{clock(segment.start)}] {LABELS[segment.source]}"
                  f"   ({latency:.2f} s after the phrase: VAD {vad_s:.2f} + queue {wait_s:.2f} + ASR {asr_s:.2f}"
                  f" + MT {mt_s:.2f}){flag}\nHY: {text}\nEN: {english}", flush=True)
            printed_at = self._now()
            latency = printed_at - segment.end
            self.latencies[segment.source].append(latency)
        self._count += 1
        if self._save_dir is not None:
            name = f"{self._count:03d}_{LABELS[segment.source]}_{segment.start:08.3f}"
            write_wav(self._save_dir / f"{name}.wav", segment.audio)
            (self._save_dir / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
            (self._save_dir / f"{name}.en.txt").write_text(english + "\n", encoding="utf-8")
        return {"source": segment.source, "label": LABELS[segment.source],
                "seg_start": f"{segment.start:.3f}", "seg_end": f"{segment.end:.3f}",
                "handed_at": f"{handed_at:.3f}", "asr_start": f"{asr_start:.3f}", "asr_end": f"{asr_end:.3f}",
                "mt_end": f"{mt_end:.3f}", "printed_at": "" if printed_at is None else f"{printed_at:.3f}",
                "latency_s": "" if latency is None else f"{latency:.3f}", "skipped": int(skipped)}


def write_wav(path: Path, audio: np.ndarray) -> None:
    """16 kHz mono 16-bit, the same format as scripts/record.py."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(np.round(np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def describe(values: list[float]) -> str:
    if not values:
        return "no phrases"
    p95 = statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]
    over = sum(v > LIMIT_S for v in values)
    return (f"{len(values)} phrases, latency p50 {statistics.median(values):.2f} s, p95 {p95:.2f} s, "
            f"max {max(values):.2f} s, {over} over {LIMIT_S:g} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true", help="print the input devices and exit")
    parser.add_argument("--mic", help="microphone: part of its name or its id (see --list)")
    parser.add_argument("--call", help="call audio, usually BlackHole: part of its name or its id")
    parser.add_argument("--threads", type=int, default=4, help="CPU threads for the ASR model")
    parser.add_argument("--save", action="store_true", help="also keep every phrase as WAV + text in logs/")
    args = parser.parse_args()
    if args.list:
        print(list_input_devices())
        return
    if not args.mic or not args.call:
        parser.error("--mic and --call are both needed (see --list)")
    try:
        devices = {SOURCE_MIC: resolve_device(args.mic), SOURCE_CALL: resolve_device(args.call)}
    except ValueError as error:
        raise SystemExit(f"error: {error}")
    if devices[SOURCE_MIC] == devices[SOURCE_CALL]:
        raise SystemExit("error: --mic and --call are the same device; --call must be BlackHole")
    names = {source: sd.query_devices(device)["name"] for source, device in devices.items()}

    print("Loading the ASR model (first start after an install ~70 s, later ~10 s)...", flush=True)
    started = time.perf_counter()
    transcriber = Transcriber(threads=args.threads)
    print(f"  loaded in {time.perf_counter() - started:.1f} s", flush=True)
    print("Loading the translation model (~4 s)...", flush=True)
    started = time.perf_counter()
    translator = Translator()
    print(f"  loaded in {time.perf_counter() - started:.1f} s (NLLB {translator.model}, beam {translator.beam_size})",
          flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    LOG_DIR.mkdir(exist_ok=True)
    csv_path = LOG_DIR / f"live_asr_{stamp}.csv"
    save_dir = LOG_DIR / f"live_asr_{stamp}" if args.save else None
    if save_dir is not None:
        save_dir.mkdir()

    session_start = time.monotonic()
    chunks: queue.Queue = queue.Queue()
    captures = {source: AudioCapture(source, device, session_start, chunks) for source, device in devices.items()}
    segmenters = {source: Segmenter(source) for source in captures}
    worker = AsrWorker(transcriber, translator, session_start, csv_path, save_dir)
    max_lag = {source: 0.0 for source in captures}
    mic_checked = call_checked = False

    # Ctrl+C only sets a flag, so it never interrupts the VAD in the middle of a chunk; the loop then
    # stops cleanly. After the first Ctrl+C the default handler is back: a second one aborts at once.
    stop = threading.Event()

    def on_ctrl_c(signum, frame) -> None:
        stop.set()
        signal.signal(signal.SIGINT, signal.default_int_handler)

    def take(chunk) -> None:
        now = time.monotonic() - session_start
        max_lag[chunk.source] = max(max_lag[chunk.source], now - (chunk.start + CHUNK_SAMPLES / SAMPLE_RATE))
        for segment in segmenters[chunk.source].feed(chunk):
            worker.inbox.put((segment, time.monotonic() - session_start))

    worker.start()
    signal.signal(signal.SIGINT, on_ctrl_c)
    print(f"\nListening. The label comes from the device the sound arrives on:\n"
          f"  Me   = [{devices[SOURCE_MIC]}] {names[SOURCE_MIC]}  (your microphone)\n"
          f"  Call = [{devices[SOURCE_CALL]}] {names[SOURCE_CALL]}  (what the call app plays to 'Call Output')\n"
          f"Ctrl+C stops (the last phrase is still transcribed).", flush=True)
    try:
        for capture in captures.values():
            capture.start()
        while not stop.is_set():
            try:
                take(chunks.get(timeout=0.2))     # wakes up regularly to check the other threads
            except queue.Empty:
                pass
            for capture in captures.values():
                capture.check()
            if worker.error is not None:
                raise RuntimeError("the ASR/MT worker failed (traceback above)") from worker.error
            if not mic_checked and time.monotonic() - session_start >= MIC_SILENCE_CHECK_S:
                mic_checked = True
                if captures[SOURCE_MIC].peak == 0.0:
                    raise SystemExit(
                        f"error: the microphone gave only digital silence for {MIC_SILENCE_CHECK_S:g} s. "
                        "Allow your terminal app in System Settings > Privacy & Security > Microphone, "
                        "then quit and reopen the terminal.")
            if not call_checked and time.monotonic() - session_start >= CALL_SILENCE_WARN_S:
                call_checked = True
                if captures[SOURCE_CALL].peak == 0.0:
                    print(f"\nWARNING: nothing has played into {names[SOURCE_CALL]!r} for {CALL_SILENCE_WARN_S:g} s, "
                          "so no 'Call' lines can appear. In the call app set the speaker to 'Call Output' "
                          "(Zoom: Settings > Audio > Speaker) and press its speaker test. If the other side is "
                          "heard from the MacBook speakers instead, their voice reaches your mic and shows up "
                          "as 'Me'.", flush=True)
    finally:   # always release the devices, also when something above raised
        for capture in captures.values():
            capture.stop()
    for capture in captures.values():
        capture.check()                           # errors from the last moments before stop()

    print("\nStopping: finishing the last phrases...", flush=True)
    while True:                                   # audio that arrived before stop() still counts
        try:
            take(chunks.get_nowait())
        except queue.Empty:
            break
    for segmenter in segmenters.values():
        for segment in segmenter.flush():
            worker.inbox.put((segment, time.monotonic() - session_start))
    worker.inbox.put(None)
    worker.join()
    if worker.error is not None:
        raise RuntimeError("the ASR/MT worker failed (traceback above)") from worker.error

    print(f"\nSession {clock(time.monotonic() - session_start)}:")
    for source in captures:
        print(f"  {LABELS[source]:4s}  {describe(worker.latencies[source])}; "
              f"{worker.skipped[source]} non-speech not printed; "
              f"{segmenters[source].dropped_short} short bursts dropped by the VAD; "
              f"{captures[source].dropouts} audio dropouts; chunk lag max {max_lag[source] * 1000:.0f} ms")
    print(f"  all   {describe(worker.latencies[SOURCE_MIC] + worker.latencies[SOURCE_CALL])}"
          + (f"; ASR max {max(worker.asr_times):.2f} s" if worker.asr_times else "")
          + (f"; MT median {statistics.median(worker.mt_times):.2f} s, max {max(worker.mt_times):.2f} s"
             if worker.mt_times else ""))
    if captures[SOURCE_CALL].peak == 0.0:
        print(f"  WARNING: {names[SOURCE_CALL]!r} was digital silence the whole time: the call app did not play to "
              "'Call Output', so nothing could be labelled 'Call'. Zoom: Settings > Audio > Speaker.")
    print(f"  log: {csv_path}" + (f"; phrases saved in {save_dir}/" if save_dir else ""))


if __name__ == "__main__":
    main()
