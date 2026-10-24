"""Speakers module: label call-side segments "Speaker 1", "Speaker 2", ... (D4).

Contract, tests and done-criteria: briefs/speakers.md
"""
import numpy as np


class SpeakerIdentifier:
    """One instance per session; labels stay stable for the whole session.
    Never returns "Me": the pipeline labels the mic side itself.

    Tuning parameters (similarity threshold, minimum length to create a new speaker)
    are added as keyword arguments with measured defaults in the speakers chat.
    """

    def __init__(self) -> None:
        raise NotImplementedError

    def identify(self, audio: np.ndarray) -> str:
        """audio: float32, mono, 16 kHz, one call-side segment.

        Always returns "Speaker N" (N = 1, 2, ... in order of first appearance).
        Called from a single thread.
        """
        raise NotImplementedError
