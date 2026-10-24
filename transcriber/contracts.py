"""Shared data types and audio constants: the contract between modules.

Every module may import from here; no module in transcriber/ imports another module.
This file is changed only in the integration chat, and every change is logged in DECISIONS.md.
"""
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000   # Hz; every module works with 16 kHz audio
CHUNK_SAMPLES = 512    # 32 ms; Silero VAD takes exactly 512 samples per call at 16 kHz

SOURCE_MIC = "mic"
SOURCE_CALL = "call"


@dataclass(frozen=True)
class AudioChunk:
    """32 ms of audio from one source. Made by audio.AudioCapture, used by vad.Segmenter."""
    source: str           # SOURCE_MIC or SOURCE_CALL
    start: float          # session seconds of the first sample
    samples: np.ndarray   # float32, shape (CHUNK_SAMPLES,), mono, 16 kHz, values in [-1, 1]


@dataclass
class Segment:
    """One spoken phrase. Made by vad.Segmenter; the pipeline fills in the other fields."""
    source: str           # SOURCE_MIC or SOURCE_CALL
    start: float          # session seconds
    end: float            # session seconds; the 5 s latency clock starts here
    audio: np.ndarray     # float32, mono, 16 kHz
    speaker: str | None = None
    hy_text: str | None = None
    en_text: str | None = None
