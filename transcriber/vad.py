"""VAD module: cut one source's AudioChunk stream into phrase Segments (Silero VAD, D2).

Contract, tests and done-criteria: briefs/vad.md
"""
import importlib.util
from collections import deque
from pathlib import Path

import numpy as np
import onnxruntime

from transcriber.contracts import (CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_CALL, SOURCE_MIC, AudioChunk,
                                   Segment)

CHUNK_SECONDS = CHUNK_SAMPLES / SAMPLE_RATE   # 0.032 s: every decision below is made per chunk

# Silero VAD at 16 kHz (checked in silero_vad/utils_vad.py, OnnxWrapper, v6.2.3):
_CONTEXT_SAMPLES = 64          # each call also sees the last 64 samples of the previous chunk
_STATE_SHAPE = (2, 1, 128)     # the model's memory between calls (batch size 1)


def _model_path() -> Path:
    """Path of silero_vad.onnx inside the installed silero-vad package.

    Found with find_spec, which locates the package WITHOUT running its __init__.py.
    Importing silero_vad would import torch and call torch.set_num_threads(1), which
    silently slows every torch model in the program (ASR, speakers).
    """
    spec = importlib.util.find_spec("silero_vad")
    if spec is None or spec.origin is None:
        raise RuntimeError("silero-vad is not installed. Run: pip install -r requirements.txt")
    path = Path(spec.origin).parent / "data" / "silero_vad.onnx"
    if not path.is_file():
        raise RuntimeError(f"{path} not found. This code expects silero-vad==6.2.3 (requirements.txt).")
    return path


class _SileroModel:
    """Silero VAD run directly with onnxruntime: one 512-sample chunk in, speech probability out.

    Does what the official silero_vad OnnxWrapper does for 16 kHz and one stream, without torch:
    put the previous chunk's last 64 samples in front, pass the model's memory (state) in, keep
    the new memory for the next call. tests/test_vad.py checks that the probabilities are equal
    to the official wrapper's. One instance per audio stream: the memory belongs to one stream.
    """

    def __init__(self) -> None:
        options = onnxruntime.SessionOptions()
        # Same as the official wrapper: one call is ~0.2 ms, more threads would only add overhead.
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(_model_path()), sess_options=options, providers=["CPUExecutionProvider"])
        self._sample_rate = np.array(SAMPLE_RATE, dtype=np.int64)
        self.reset()

    def reset(self) -> None:
        """Forget the stream: start as if no audio had been heard yet."""
        self._state = np.zeros(_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros(_CONTEXT_SAMPLES, dtype=np.float32)

    def __call__(self, samples: np.ndarray) -> float:
        """Speech probability (0..1) of the next CHUNK_SAMPLES float32 samples of the stream."""
        if samples.shape != (CHUNK_SAMPLES,) or samples.dtype != np.float32:
            raise ValueError(f"expected float32 samples of shape ({CHUNK_SAMPLES},), "
                             f"got {samples.dtype} {samples.shape}")
        model_input = np.concatenate([self._context, samples])[np.newaxis, :]   # shape (1, 576)
        probability, self._state = self._session.run(
            None, {"input": model_input, "state": self._state, "sr": self._sample_rate})
        self._context = samples[-_CONTEXT_SAMPLES:].copy()
        return float(probability[0, 0])




def _to_chunks(milliseconds: float) -> int:
    """A duration rounded to whole 32 ms chunks."""
    return round(milliseconds / 1000 / CHUNK_SECONDS)


class Segmenter:
    """Push-based segmenter for ONE source. No threads, no queues, no clock reads:
    all times come from chunk.start, so a WAV file and live audio behave the same.

    Each chunk gets a speech probability p from Silero and is one of:
      speech   p >= threshold
      silence  p <  neg_threshold
      unsure   in between: keeps the current state (hysteresis), so a score that
               wobbles around one value does not start and stop phrases.

    Rules (durations are rounded to whole 32 ms chunks):
      start     the first speech chunk starts a phrase; the last pad_ms of audio before it
                (pre-roll) is put in front, so the first syllable is not cut.
      end       min_silence_ms after the first silence chunk that follows the last speech
                chunk (unsure chunks do not interrupt that wait, speech does). The segment
                keeps pad_ms of audio after the last speech chunk.
      long      once a phrase is longer than soft_max_s, the first dip of min_dip_ms
                (chunks below threshold) ends it, cut in the middle of the dip, as soon as
                the dip is long enough. This keeps nonstop speech flowing out with almost no
                wait (a pause of min_silence_ms may never come). 96 ms is longer than the
                closure inside a consonant, so the cut should fall between words.
      too long  with no such dip, the phrase is cut at max_segment_s, at the quietest chunk
                (lowest RMS) of the last quiet_search_ms. In fluent speech Silero stays
                above threshold for 10 s and more, but the gaps between words are still
                20-35 dB quieter than the words (measured). The audio after the cut goes
                on as the next phrase; pieces never overlap and never leave audio out.
      too short phrases with less than min_speech_ms from the first to the last speech
                chunk are dropped and counted in dropped_short.

    Segment.start/end are the times of the first/last sample of Segment.audio, so
    end - start == len(audio) / SAMPLE_RATE. Defaults are starting values, tuned in
    piece 4 (DECISIONS.md D2).
    """

    def __init__(self, source: str, *, threshold: float = 0.5, neg_threshold: float = 0.35,
                 min_silence_ms: float = 500, pad_ms: float = 200, soft_max_s: float = 5.0,
                 min_dip_ms: float = 96, max_segment_s: float = 10.0,
                 quiet_search_ms: float = 1000, min_speech_ms: float = 250) -> None:
        if source not in (SOURCE_MIC, SOURCE_CALL):
            raise ValueError(f"source must be {SOURCE_MIC!r} or {SOURCE_CALL!r}, got {source!r}")
        if not 0 < neg_threshold < threshold < 1:
            raise ValueError(f"need 0 < neg_threshold < threshold < 1, got {neg_threshold}, {threshold}")
        self.source = source
        self._threshold = threshold
        self._neg_threshold = neg_threshold
        self._min_silence = _to_chunks(min_silence_ms)
        self._pad = _to_chunks(pad_ms)
        self._soft_chunks = int(soft_max_s / CHUNK_SECONDS)
        self._min_dip = _to_chunks(min_dip_ms)
        self._max_chunks = int(max_segment_s / CHUNK_SECONDS)   # rounded down: never longer than asked
        self._quiet_search = _to_chunks(quiet_search_ms)
        self._min_speech = _to_chunks(min_speech_ms)
        if min(self._min_silence, self._min_dip, self._quiet_search, self._min_speech) < 1 or self._pad < 0:
            raise ValueError("min_silence_ms, min_dip_ms, quiet_search_ms and min_speech_ms must be at least "
                             "one chunk (32 ms), pad_ms must not be negative")
        if self._quiet_search > self._max_chunks - self._soft_chunks:
            raise ValueError(f"quiet_search_ms={quiet_search_ms} must not be longer than "
                             f"max_segment_s - soft_max_s")
        if not self._pad + self._min_speech < self._soft_chunks < self._max_chunks:
            raise ValueError(f"need pad_ms + min_speech_ms < soft_max_s < max_segment_s, got "
                             f"{pad_ms} ms, {min_speech_ms} ms, {soft_max_s} s, {max_segment_s} s")

        self._model = _SileroModel()
        self._dropped_short = 0
        self._next_start: float | None = None      # where the next chunk must start (gap check)
        # Current phrase: its chunks and their probabilities. Empty = waiting for speech.
        self._chunks: list[AudioChunk] = []
        self._probs: list[float] = []
        self._silence_from: int | None = None      # index of the silence chunk that started the wait
        self._dip = 0                              # chunks below threshold in a row, up to now
        # While waiting: the last pad chunks, to put in front of the next phrase.
        self._preroll: deque[tuple[AudioChunk, float]] = deque(maxlen=self._pad)

    @property
    def dropped_short(self) -> int:
        """Speech bursts thrown away for being shorter than the minimum segment length."""
        return self._dropped_short

    def feed(self, chunk: AudioChunk) -> list[Segment]:
        """Process one chunk. Return the segments that finished with it (usually none).

        Segment.end is the end of the speech (plus padding), not the moment the
        silence was confirmed: the 5 s latency clock starts at Segment.end.
        """
        self._check(chunk)
        p = self._model(chunk.samples)      # raises on a wrong chunk shape/type
        self._next_start = chunk.start + CHUNK_SECONDS

        if not self._chunks:                # waiting for speech
            if p >= self._threshold:
                self._chunks = [c for c, _ in self._preroll] + [chunk]
                self._probs = [q for _, q in self._preroll] + [p]
                self._preroll.clear()
                self._silence_from = None
                self._dip = 0
            else:
                self._preroll.append((chunk, p))
            return []

        self._chunks.append(chunk)          # inside a phrase
        self._probs.append(p)
        if p >= self._threshold:
            self._silence_from = None
            self._dip = 0
        else:
            self._dip += 1
            if p < self._neg_threshold and self._silence_from is None:
                self._silence_from = len(self._chunks) - 1

        if self._silence_from is not None and len(self._chunks) - self._silence_from >= self._min_silence:
            return self._close()
        if len(self._chunks) >= self._soft_chunks and self._dip >= self._min_dip:
            return self._cut(len(self._chunks) - self._dip + self._dip // 2)   # middle of the dip
        if len(self._chunks) >= self._max_chunks:
            return self._cut(self._quietest_recent())                          # no dip: quietest point
        return []

    def flush(self) -> list[Segment]:
        """End of stream: return the segment still in progress, if any."""
        segments = self._close() if self._chunks else []
        self._model.reset()
        self._preroll.clear()
        self._next_start = None
        return segments

    def _check(self, chunk: AudioChunk) -> None:
        if chunk.source != self.source:
            raise ValueError(f"Segmenter for {self.source!r} got a chunk from {chunk.source!r}")
        if self._next_start is not None and abs(chunk.start - self._next_start) > 0.5 / SAMPLE_RATE:
            raise ValueError(f"{self.source}: chunk starts at {chunk.start:.6f} s, expected "
                             f"{self._next_start:.6f} s; chunks must arrive in order without gaps")

    def _close(self) -> list[Segment]:
        """The phrase is over: keep pad chunks after the last speech chunk, the rest is pre-roll."""
        last_speech = max(i for i, q in enumerate(self._probs) if q >= self._threshold)
        end = min(last_speech + self._pad + 1, len(self._chunks))
        segments = self._emit(self._chunks[:end], self._probs[:end])
        self._wait_again(self._chunks[end:], self._probs[end:])
        return segments

    def _cut(self, cut: int) -> list[Segment]:
        """Long phrase: chunks before index `cut` become a segment. The rest goes on as the
        next phrase if it holds speech (after a hard cut), else it becomes pre-roll."""
        segments = self._emit(self._chunks[:cut], self._probs[:cut])
        rest, rest_probs = self._chunks[cut:], self._probs[cut:]
        speech = [i for i, q in enumerate(rest_probs) if q >= self._threshold]
        if not speech:
            self._wait_again(rest, rest_probs)
            return segments
        self._chunks, self._probs = rest, rest_probs
        after = [i for i in range(speech[-1] + 1, len(rest_probs)) if rest_probs[i] < self._neg_threshold]
        self._silence_from = after[0] if after else None
        self._dip = len(rest_probs) - speech[-1] - 1
        return segments

    def _quietest_recent(self) -> int:
        """Index of the quietest chunk (lowest RMS) among the last quiet_search chunks;
        the latest one wins a tie, so the piece is handed over as early as possible."""
        first = len(self._chunks) - self._quiet_search
        loudness = [float(np.sqrt(np.mean(np.square(c.samples)))) for c in self._chunks[first:]]
        return first + max(range(len(loudness)), key=lambda i: (-loudness[i], i))

    def _wait_again(self, rest: list[AudioChunk], rest_probs: list[float]) -> None:
        """Back to waiting for speech. `rest` is audio after a cut that holds no speech: trailing
        silence or the second half of a dip. Its last pad chunks become the next pre-roll."""
        self._chunks, self._probs, self._silence_from, self._dip = [], [], None, 0
        self._preroll.extend(zip(rest, rest_probs))      # the deque keeps only the last pad chunks

    def _emit(self, chunks: list[AudioChunk], probs: list[float]) -> list[Segment]:
        speech = [i for i, q in enumerate(probs) if q >= self._threshold]
        if not speech or speech[-1] - speech[0] + 1 < self._min_speech:
            self._dropped_short += 1
            return []
        return [Segment(source=self.source, start=chunks[0].start,
                        end=chunks[-1].start + CHUNK_SECONDS,
                        audio=np.concatenate([c.samples for c in chunks]))]
