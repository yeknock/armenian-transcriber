"""Audio module: find input devices and capture them as 16 kHz mono AudioChunks.

Contract, tests and done-criteria: briefs/audio.md
"""
import queue

from transcriber.contracts import AudioChunk


def list_input_devices() -> str:
    """Return a printable table of input devices: id, name, input channels, default sample rate."""
    raise NotImplementedError


def resolve_device(spec: str) -> int:
    """Turn a device id ("3") or a case-insensitive part of its name ("blackhole") into a device id.

    Raises ValueError if nothing matches, if more than one device matches,
    or if the device has no input channels. The message lists the candidates.
    """
    raise NotImplementedError


class AudioCapture:
    """Captures one input device and puts AudioChunks for `source` on `out`.

    - every chunk holds exactly CHUNK_SAMPLES float32 samples, mono, 16 kHz
    - chunk.start = seconds since `session_start` (one time.monotonic() value shared by
      both sources), counted from samples received, so it does not drift
    - the sounddevice callback only copies data; resampling and chunking run outside it
    """

    def __init__(self, source: str, device: int, session_start: float,
                 out: queue.Queue[AudioChunk]) -> None:
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        """Stop and close the stream."""
        raise NotImplementedError

    @property
    def dropouts(self) -> int:
        """Overflow/underflow reports from the audio driver since start()."""
        raise NotImplementedError

    @property
    def peak(self) -> float:
        """Loudest absolute sample since start(). 0.0 means only digital silence
        (usually a missing macOS Microphone permission or wrong routing)."""
        raise NotImplementedError
