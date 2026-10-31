"""Tests for the VAD module (briefs/vad.md). Run from the repo root:
    python -m unittest tests.test_vad -v
"""
import subprocess
import sys
import unittest
import wave
from pathlib import Path

import numpy as np

from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE
from transcriber.vad import _SileroModel

REPO = Path(__file__).resolve().parents[1]
RECORDINGS = sorted((REPO / "eval" / "audio").glob("*.wav"))   # git-ignored, may be missing


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"{path}: expected 16 kHz mono 16-bit (scripts/record.py writes that)")
        return np.frombuffer(wav.readframes(wav.getnframes()), "<i2").astype(np.float32) / 32768


def chunks(audio: np.ndarray) -> list[np.ndarray]:
    return [audio[i:i + CHUNK_SAMPLES] for i in range(0, len(audio) - CHUNK_SAMPLES + 1, CHUNK_SAMPLES)]


def generated_audio(seconds: float = 4.0) -> np.ndarray:
    """Noise plus a pulsing tone: not speech, but enough to exercise the model's memory."""
    rng = np.random.default_rng(0)
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    tone = 0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)
    return (tone + 0.05 * rng.standard_normal(len(t))).astype(np.float32)


def ours(audio: np.ndarray) -> np.ndarray:
    model = _SileroModel()
    return np.array([model(c) for c in chunks(audio)])


def official(audio: np.ndarray) -> np.ndarray:
    """Silero's own wrapper (imports torch). Used only here, as the reference."""
    import torch
    from silero_vad import load_silero_vad
    model = load_silero_vad(onnx=True)
    return np.array([model(torch.from_numpy(c.copy()), SAMPLE_RATE).item() for c in chunks(audio)])


class SileroModelTest(unittest.TestCase):

    def test_matches_official_wrapper_on_recordings(self):
        if not RECORDINGS:
            self.skipTest("no WAV in eval/audio/; record one with scripts/record.py")
        for path in RECORDINGS:
            with self.subTest(path.name):
                audio = read_wav(path)
                difference = np.abs(ours(audio) - official(audio)).max()
                self.assertLessEqual(difference, 1e-6)

    def test_matches_official_wrapper_on_generated_audio(self):
        audio = generated_audio()
        self.assertLessEqual(np.abs(ours(audio) - official(audio)).max(), 1e-6)

    def test_reset_starts_the_stream_again(self):
        audio = generated_audio()
        model = _SileroModel()
        first = [model(c) for c in chunks(audio)]
        model.reset()
        second = [model(c) for c in chunks(audio)]
        self.assertEqual(first, second)

    def test_two_streams_do_not_share_memory(self):
        a, b = generated_audio(), np.flip(generated_audio()).copy()
        model_a, model_b = _SileroModel(), _SileroModel()
        interleaved_a, interleaved_b = [], []
        for chunk_a, chunk_b in zip(chunks(a), chunks(b)):   # mic and call side, chunk by chunk
            interleaved_a.append(model_a(chunk_a))
            interleaved_b.append(model_b(chunk_b))
        self.assertEqual(interleaved_a, list(ours(a)))
        self.assertEqual(interleaved_b, list(ours(b)))

    def test_rejects_wrong_chunks(self):
        model = _SileroModel()
        with self.assertRaises(ValueError):
            model(np.zeros(CHUNK_SAMPLES - 1, dtype=np.float32))    # wrong length
        with self.assertRaises(ValueError):
            model(np.zeros(CHUNK_SAMPLES, dtype=np.float64))        # wrong type

    def test_does_not_import_torch(self):
        # A fresh Python process, because this test file itself imports torch for the reference.
        code = ("import sys; from transcriber.vad import _SileroModel; _SileroModel(); "
                "sys.exit(1 if 'torch' in sys.modules else 0)")
        result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, "torch was imported\n" + result.stderr)


if __name__ == "__main__":
    unittest.main()
