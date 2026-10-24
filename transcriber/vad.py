"""VAD module: cut one source's AudioChunk stream into phrase Segments (Silero VAD, D2).

Contract, tests and done-criteria: briefs/vad.md
"""
from transcriber.contracts import AudioChunk, Segment


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
