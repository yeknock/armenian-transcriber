"""ASR module: Armenian speech -> Armenian text (nvidia/stt_hy_fastconformer_hybrid_large_pc, D1).

Contract, tests and done-criteria: briefs/asr.md
"""
import numpy as np


class Transcriber:
    def __init__(self) -> None:
        """Load the model once (slow). Raise if it cannot be loaded. No network after the first download."""
        raise NotImplementedError

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32, mono, 16 kHz, about 0.3-15 s; not modified.

        Return Armenian text with punctuation; "" only when the model outputs nothing.
        Called from a single worker thread.
        """
        raise NotImplementedError
