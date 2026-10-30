"""Audio module: find input devices and capture them as 16 kHz mono AudioChunks.

Contract, tests and done-criteria: briefs/audio.md
"""
import queue
import threading
import time

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

    Data flow: sounddevice callback (audio thread: copy block -> raw queue)
               -> worker thread (_Rechunker: mono, 16 kHz, 512-sample chunks) -> `out`.
    Errors on those threads do not reach the main thread by themselves, so the owner
    calls check() regularly, and once more after stop().
    """

    def __init__(self, source: str, device: int, session_start: float,
                 out: queue.Queue[AudioChunk]) -> None:
        info = sd.query_devices(device)
        if info["max_input_channels"] < 1:
            raise ValueError(f"Device {device} {info['name']!r} has no input channels.")
        self._source = source
        self._device_name = info["name"]
        self._rate = int(info["default_samplerate"])        # capture at the device's own rate
        self._channels = min(2, info["max_input_channels"])  # mono or stereo; averaged to mono later
        self._session_start = session_start
        self._out = out
        self._raw: queue.Queue = queue.Queue()  # (callback time, block) or None = stop
        self._dropouts = 0
        self._peak = 0.0
        self._error: Exception | None = None
        self._running = False
        # latency="low": with sounddevice's default "high", BlackHole delivers 4096-frame blocks
        # (85 ms), so call audio reaches us up to 85 ms later; "low" gives 480 frames (10 ms).
        # The mic goes from 512 to 64 frames. Measured on the MacBook Air M1, 2026-10-30.
        # Cost: many more callbacks; watch `dropouts` under full load (TESTS.md).
        self._stream = sd.InputStream(device=device, samplerate=self._rate, channels=self._channels,
                                      dtype="float32", latency="low", callback=self._callback)
        self._worker = threading.Thread(target=self._work, name=f"audio-{source}", daemon=True)

    def _callback(self, indata, frames, time_info, status) -> None:
        # Audio thread: must stay short and never wait. PortAudio reuses `indata`, so copy it.
        if status:
            self._dropouts += 1
        self._raw.put((time.monotonic(), indata.copy()))

    def _work(self) -> None:
        try:
            rechunker = None
            while (item := self._raw.get()) is not None:
                callback_time, block = item
                if rechunker is None:
                    # The first callback runs right after its block was recorded, so the
                    # block's first sample is about one block length earlier.
                    t0 = callback_time - len(block) / self._rate - self._session_start
                    rechunker = _Rechunker(self._source, self._rate, self._channels, t0)
                self._peak = max(self._peak, float(np.max(np.abs(block))))
                for chunk in rechunker.push(block):
                    self._out.put(chunk)
        except Exception as error:   # kept, not swallowed: check() raises it on the main thread
            self._error = error

    def start(self) -> None:
        self._worker.start()
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        """Stop and close the stream and end the worker; safe to call after a failure.
        Errors are raised by check(), not here. A last partial chunk (< 32 ms) is dropped."""
        self._running = False
        self._stream.stop()
        self._stream.close()
        if self._worker.is_alive():
            self._raw.put(None)
            self._worker.join()

    def check(self) -> None:
        """Raise RuntimeError if capture has failed (worker error or the stream stopped by itself)."""
        if self._error is not None:
            raise RuntimeError(f"audio capture for {self._source!r} ({self._device_name!r}) failed: "
                               f"{self._error!r}") from self._error
        if self._running and not self._stream.active:
            raise RuntimeError(f"audio stream for {self._source!r} ({self._device_name!r}) stopped "
                               f"unexpectedly; see the error printed above.")

    @property
    def dropouts(self) -> int:
        """Overflow/underflow reports from the audio driver since start()."""
        return self._dropouts

    @property
    def peak(self) -> float:
        """Loudest absolute sample since start(). 0.0 means only digital silence
        (usually a missing macOS Microphone permission or wrong routing)."""
        return self._peak
