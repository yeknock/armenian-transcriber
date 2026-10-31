"""VAD module: cut one source's AudioChunk stream into phrase Segments (Silero VAD, D2).

Contract, tests and done-criteria: briefs/vad.md
"""
import importlib.util
from pathlib import Path

import numpy as np
import onnxruntime

from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, AudioChunk, Segment

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


class Segmenter:
    """Push-based segmenter for ONE source. No threads, no queues, no clock reads:
    all times come from chunk.start, so a WAV file and live audio behave the same.

    Tuning parameters (threshold, min silence, padding, max/min segment length) are
    added as keyword arguments with measured defaults in the VAD chat.
    """

    def __init__(self, source: str) -> None:
        raise NotImplementedError

    def feed(self, chunk: AudioChunk) -> list[Segment]:
        """Process one chunk. Return the segments that finished with it (usually none).

        Segment.end is the end of the speech (plus padding), not the moment the
        silence was confirmed: the 5 s latency clock starts at Segment.end.
        """
        raise NotImplementedError

    def flush(self) -> list[Segment]:
        """End of stream: return the segment still in progress, if any."""
        raise NotImplementedError

    @property
    def dropped_short(self) -> int:
        """Speech bursts thrown away for being shorter than the minimum segment length."""
        raise NotImplementedError
