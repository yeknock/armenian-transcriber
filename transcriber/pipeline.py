"""Pipeline: wires the modules into the live program (D5, briefs/integration.md). The only module that imports others.

    Mic ───────► AudioCapture ─► Segmenter ─────────────────────────┐
                                                                    ├─► worker: ASR ─► speaker ─► MT ─► print
    BlackHole ─► AudioCapture ─► Segmenter ─────────────────────────┘

- The main thread takes the 32 ms chunks of both captures, feeds each source's Segmenter (push-based, no thread of
  its own) and checks the other threads every 0.2 s.
- One worker thread runs the models, one phrase at a time, in the order the phrases ended: ASR first; the ASR's text
  for a cough or "hmm" (mt.is_non_speech) is not printed and gets no speaker (D3b); then the speaker (mic = "Me",
  call side = SpeakerIdentifier); then MT; then it prints the entry. It is the only thread that prints entries.
- An error in any thread stops the program with that error (nothing fails silently).
- Every printed entry adds a row to logs/latency.csv (MODULES.md "Shared formats"); latency = printed_at - seg_end.
"""
import csv
import queue
import statistics
import threading
import time
from pathlib import Path

from transcriber.asr import Transcriber
from transcriber.audio import AudioCapture
from transcriber.contracts import SOURCE_CALL, SOURCE_MIC, Segment
from transcriber.mt import Translator, is_non_speech
from transcriber.output import format_entry
from transcriber.speakers import SpeakerIdentifier
from transcriber.vad import Segmenter

ME = "Me"
LIMIT_S = 5.0                 # the brief: at most 5 s from the end of a phrase to its English line
MIC_SILENCE_CHECK_S = 3.0     # the mic giving only exact zeros this long = missing macOS permission
CALL_SILENCE_WARN_S = 10.0    # BlackHole giving only exact zeros this long = the call app plays somewhere else
LATENCY_CSV = Path("logs") / "latency.csv"
LATENCY_FIELDS = ["source", "speaker", "seg_start", "seg_end", "asr_s", "speaker_s", "mt_s", "printed_at"]


class MicrophoneSilent(RuntimeError):
    """The microphone delivered only digital silence: macOS did not give the terminal microphone access."""


class _Worker(threading.Thread):
    """Takes Segments from `inbox` (None ends it); ASR, speaker, MT, print, CSV row. An error is kept in `error`."""

    def __init__(self, transcriber: Transcriber, speakers: SpeakerIdentifier, translator: Translator,
                 session_start: float, csv_path: Path) -> None:
        super().__init__(name="worker", daemon=True)
        self.inbox: queue.Queue = queue.Queue()      # unbounded: a phrase is never dropped
        self.error: Exception | None = None
        self.latencies: dict[str, list[float]] = {SOURCE_MIC: [], SOURCE_CALL: []}
        self.skipped: dict[str, int] = {SOURCE_MIC: 0, SOURCE_CALL: 0}
        self._transcriber, self._speakers, self._translator = transcriber, speakers, translator
        self._session_start = session_start
        self._csv_path = csv_path

    def _now(self) -> float:
        return time.monotonic() - self._session_start

    def run(self) -> None:
        try:
            self._csv_path.parent.mkdir(exist_ok=True)
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                rows = csv.DictWriter(f, fieldnames=LATENCY_FIELDS)
                rows.writeheader()
                while (segment := self.inbox.get()) is not None:
                    row = self._process(segment)
                    if row is not None:
                        rows.writerow(row)
                        f.flush()
        except Exception as error:      # kept for the main thread, which raises it
            self.error = error

    def _process(self, segment: Segment) -> dict | None:
        started = self._now()
        hy_text = self._transcriber.transcribe(segment.audio)
        asr_done = self._now()
        if not hy_text or is_non_speech(hy_text):        # a cough / "hmm" / breath: nothing to show (D3b)
            self.skipped[segment.source] += 1
            return None
        speaker = ME if segment.source == SOURCE_MIC else self._speakers.identify(segment.audio)
        speaker_done = self._now()
        en_text = self._translator.translate(hy_text)
        mt_done = self._now()
        print(format_entry(segment.start, speaker, hy_text, en_text), flush=True)
        printed_at = self._now()
        self.latencies[segment.source].append(printed_at - segment.end)
        return {"source": segment.source, "speaker": speaker, "seg_start": f"{segment.start:.3f}",
                "seg_end": f"{segment.end:.3f}", "asr_s": f"{asr_done - started:.3f}",
                "speaker_s": f"{speaker_done - asr_done:.3f}", "mt_s": f"{mt_done - speaker_done:.3f}",
                "printed_at": f"{printed_at:.3f}"}


class Pipeline:
    """One live session: two devices in, entries printed. Models are loaded by the caller (slow) and passed in."""

    def __init__(self, mic_device: int, call_device: int, transcriber: Transcriber, speakers: SpeakerIdentifier,
                 translator: Translator, csv_path: Path = LATENCY_CSV) -> None:
        if mic_device == call_device:
            raise ValueError("the microphone and the call input are the same device; the call input must be BlackHole")
        self._session_start = time.monotonic()
        self._chunks: queue.Queue = queue.Queue()
        self._captures = {SOURCE_MIC: AudioCapture(SOURCE_MIC, mic_device, self._session_start, self._chunks),
                          SOURCE_CALL: AudioCapture(SOURCE_CALL, call_device, self._session_start, self._chunks)}
        self._segmenters = {source: Segmenter(source) for source in self._captures}
        self._speakers = speakers
        self._worker = _Worker(transcriber, speakers, translator, self._session_start, csv_path)
        self.csv_path = csv_path

    def _seconds(self) -> float:
        return time.monotonic() - self._session_start

    def _take(self, chunk) -> None:
        for segment in self._segmenters[chunk.source].feed(chunk):
            self._worker.inbox.put(segment)

    def _check_threads(self) -> None:
        for capture in self._captures.values():
            capture.check()
        if self._worker.error is not None:
            raise RuntimeError("the worker (ASR / speakers / MT) failed") from self._worker.error

    def run(self, stop: threading.Event) -> None:
        """Listen until `stop` is set, then finish the phrases already heard. Raises if anything failed."""
        self._worker.start()
        mic_checked = call_checked = False
        try:
            for capture in self._captures.values():
                capture.start()
            while not stop.is_set():
                try:
                    self._take(self._chunks.get(timeout=0.2))     # wakes up regularly to check the threads
                except queue.Empty:
                    pass
                self._check_threads()
                if not mic_checked and self._seconds() >= MIC_SILENCE_CHECK_S:
                    mic_checked = True
                    if self._captures[SOURCE_MIC].peak == 0.0:
                        raise MicrophoneSilent(
                            f"the microphone gave only digital silence for {MIC_SILENCE_CHECK_S:g} s. Allow your "
                            "terminal app in System Settings > Privacy & Security > Microphone, then quit and reopen "
                            "the terminal.")
                if not call_checked and self._seconds() >= CALL_SILENCE_WARN_S:
                    call_checked = True
                    if self._captures[SOURCE_CALL].peak == 0.0:
                        print(f"WARNING: nothing has played into the call input for {CALL_SILENCE_WARN_S:g} s. In the "
                              "call app set the speaker to 'Call Output' (Zoom: Settings > Audio > Speaker).\n",
                              flush=True)
        finally:                                  # always release the devices, also when something above raised
            for capture in self._captures.values():
                capture.stop()
        for capture in self._captures.values():
            capture.check()                       # errors from the last moments before stop()
        while True:                               # audio that arrived before stop() still counts
            try:
                self._take(self._chunks.get_nowait())
            except queue.Empty:
                break
        for segmenter in self._segmenters.values():
            for segment in segmenter.flush():
                self._worker.inbox.put(segment)
        self._worker.inbox.put(None)
        self._worker.join()
        if self._worker.error is not None:
            raise RuntimeError("the worker (ASR / speakers / MT) failed") from self._worker.error

    def summary(self) -> str:
        """Latency p50 / p95 / max per side and in total, plus what was not printed."""
        lines = [f"Session {self._seconds():.0f} s; {self._speakers.speakers_found} call-side speaker(s) found."]
        everything = []
        for source, label in ((SOURCE_MIC, "Me  "), (SOURCE_CALL, "Call")):
            values = self._worker.latencies[source]
            everything += values
            lines.append(f"  {label} {_describe(values)}; {self._worker.skipped[source]} non-speech not printed; "
                         f"{self._captures[source].dropouts} audio dropouts")
        lines.append(f"  all  {_describe(everything)}")
        lines.append(f"  latency log: {self.csv_path}")
        return "\n".join(lines)


def _describe(values: list[float]) -> str:
    if not values:
        return "no phrases"
    p95 = statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]
    over = sum(v > LIMIT_S for v in values)
    return (f"{len(values)} phrases, latency p50 {statistics.median(values):.2f} s, p95 {p95:.2f} s, "
            f"max {max(values):.2f} s, {over} over {LIMIT_S:g} s")
