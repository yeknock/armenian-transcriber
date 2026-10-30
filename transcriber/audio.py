"""Audio module: find input devices and capture them as 16 kHz mono AudioChunks.

Contract, tests and done-criteria: briefs/audio.md
"""
import queue

import numpy as np
import sounddevice as sd
import soxr

from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, AudioChunk


def _device_line(device: dict) -> str:
    return (f"{device['index']:>3}  {device['name']:<40} "
            f"{device['max_input_channels']:>6}  {device['default_samplerate']:>9.0f}")


def list_input_devices() -> str:
    """Return a printable table of input devices: id, name, input channels, default sample rate."""
    header = f"{'id':>3}  {'name':<40} {'inputs':>6}  {'rate (Hz)':>9}"
    rows = [_device_line(d) for d in sd.query_devices() if d["max_input_channels"] > 0]
    if not rows:
        rows = ["(no input devices found)"]
    return "\n".join([header, *rows])


def resolve_device(spec: str) -> int:
    """Turn a device id ("3") or a case-insensitive part of its name ("blackhole") into a device id.

    Raises ValueError if nothing matches, if more than one device matches,
    or if the device has no input channels. The message lists the candidates.
    """
    devices = sd.query_devices()

    if spec.strip().isdigit():
        device_id = int(spec)
        if device_id >= len(devices):
            raise ValueError(f"There is no audio device with id {device_id}.\n"
                             f"Input devices:\n{list_input_devices()}")
        device = devices[device_id]
    else:
        needle = spec.strip().casefold()
        exact = [d for d in devices if d["name"].casefold() == needle]
        partial = [d for d in devices if needle in d["name"].casefold()]
        matches = exact or partial   # a full-name match wins over part-of-name matches
        if not matches:
            raise ValueError(f"No audio device name contains {spec!r}.\n"
                             f"Input devices:\n{list_input_devices()}")
        if len(matches) > 1:
            candidates = "\n".join(_device_line(d) for d in matches)
            raise ValueError(f"{spec!r} matches {len(matches)} devices; use a longer part of "
                             f"the name or the id.\nMatching devices:\n{candidates}")
        device = matches[0]

    if device["max_input_channels"] < 1:
        raise ValueError(f"Device {device['index']} {device['name']!r} has no input channels "
                         f"(it is an output-only device).\nInput devices:\n{list_input_devices()}")
    return device["index"]


class _Rechunker:
    """Turns device blocks into AudioChunks: mix to mono -> resample to 16 kHz -> cut into CHUNK_SAMPLES.

    No threads and no sounddevice here, so it can be tested with generated audio
    (python -m scripts.try_audio --selftest).

    - One soxr.ResampleStream keeps the filter state between blocks, so block borders give
      no clicks: the output is identical to resampling the whole recording at once.
    - soxr compensates its own delay: output sample n belongs to input time n / 16000.
      It only holds back a few ms of samples until it has seen enough input.
    - chunk.start = t0 + (16 kHz samples already emitted) / 16000, so it cannot drift.
    """

    def __init__(self, source: str, in_rate: int, channels: int, t0: float) -> None:
        self._source = source
        self._channels = channels
        self._t0 = t0
        self._resampler = soxr.ResampleStream(in_rate, SAMPLE_RATE, 1, dtype="float32")
        self._buffer = np.zeros(0, dtype=np.float32)
        self._emitted = 0   # 16 kHz samples already handed out as chunks

    def push(self, block: np.ndarray) -> list[AudioChunk]:
        """Take one float32 block of shape (frames, channels); return the chunks that are now complete."""
        if block.dtype != np.float32 or block.ndim != 2 or block.shape[1] != self._channels:
            raise ValueError(f"expected float32 block of shape (frames, {self._channels}), "
                             f"got {block.dtype} {block.shape}")
        mono = block.mean(axis=1, dtype=np.float32)
        resampled = self._resampler.resample_chunk(mono)
        # The resampling filter can overshoot slightly on full-scale input (measured: 1.17 for a
        # full-scale square wave); the contract promises values in [-1, 1].
        np.clip(resampled, -1.0, 1.0, out=resampled)
        self._buffer = np.concatenate([self._buffer, resampled])

        chunks = []
        while len(self._buffer) >= CHUNK_SAMPLES:
            samples = self._buffer[:CHUNK_SAMPLES].copy()
            self._buffer = self._buffer[CHUNK_SAMPLES:]
            start = self._t0 + self._emitted / SAMPLE_RATE
            chunks.append(AudioChunk(source=self._source, start=start, samples=samples))
            self._emitted += CHUNK_SAMPLES
        return chunks


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
