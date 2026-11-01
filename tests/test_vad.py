"""Tests for the VAD module (briefs/vad.md). Run from the repo root:
    python -m unittest tests.test_vad -v
"""
import subprocess
import sys
import unittest
import wave
from pathlib import Path

import numpy as np

from transcriber.contracts import CHUNK_SAMPLES, SAMPLE_RATE, SOURCE_CALL, SOURCE_MIC, AudioChunk
from transcriber.vad import CHUNK_SECONDS, Segmenter, _SileroModel

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


# ---------------------------------------------------------------- Segmenter rules
# These rule tests use soft_max_s=5 / max_segment_s=10 (RULE_TUNING, also the program's defaults, D2; set explicitly so
# the tests stay valid if the defaults change). So: wait 16 chunks of silence, pad 6 chunks, min speech 8 chunks,
# early cut after 156 chunks (5 s) at a dip of 3 chunks, hard cut at 312 chunks (10 s) at the
# quietest of the last 31 chunks (1 s).
S, Q, U = 0.9, 0.1, 0.4      # speech, silence (quiet), unsure (between 0.35 and 0.5)
T0 = 5.0                     # session time of the first chunk; not 0, so wrong time maths shows


class FakeModel:
    """Returns the probabilities it was given, one per call, instead of running Silero."""

    def __init__(self, probs):
        self.probs = list(probs)

    def __call__(self, samples):
        return self.probs.pop(0)

    def reset(self):
        pass


LOUD = 0.3                   # loudness of every fake chunk, unless the test makes some quiet
RULE_TUNING = {"soft_max_s": 5.0, "max_segment_s": 10.0}


def run(probs, source=SOURCE_MIC, flush=True, quiet=(), **tuning):
    """Feed one chunk per probability. Chunk i's first sample is i / 10000, so a segment's audio
    tells exactly which chunks it holds; its other samples are LOUD, or 0.001 for indices in `quiet`.
    Returns (segments, [chunk index of each return], segmenter)."""
    segmenter = Segmenter(source, **{**RULE_TUNING, **tuning})
    segmenter._model = FakeModel(probs)
    segments, returned_at = [], []
    for i in range(len(probs)):
        samples = np.full(CHUNK_SAMPLES, 0.001 if i in quiet else LOUD, np.float32)
        samples[0] = i / 10000
        chunk = AudioChunk(source, T0 + i * CHUNK_SECONDS, samples)
        for segment in segmenter.feed(chunk):
            segments.append(segment)
            returned_at.append(i)
    if flush:
        segments += segmenter.flush()
    return segments, returned_at, segmenter


def held(segment):
    """Chunk indices inside a segment's audio."""
    return [round(v * 10000) for v in segment.audio[::CHUNK_SAMPLES]]


class SegmenterTest(unittest.TestCase):

    def assertWellFormed(self, segments):
        for segment in segments:
            self.assertEqual(segment.audio.dtype, np.float32)
            self.assertAlmostEqual(segment.end - segment.start, len(segment.audio) / SAMPLE_RATE, places=9)
            indices = held(segment)
            self.assertEqual(indices, list(range(indices[0], indices[-1] + 1)))     # no holes
            self.assertAlmostEqual(segment.start, T0 + indices[0] * CHUNK_SECONDS, places=9)

    def test_silence_gives_nothing(self):
        segments, _, segmenter = run([Q] * 500)
        self.assertEqual(segments, [])
        self.assertEqual(segmenter.dropped_short, 0)

    def test_one_phrase_with_preroll_and_padding(self):
        segments, returned_at, _ = run([Q] * 20 + [S] * 30 + [Q] * 30, flush=False)
        self.assertEqual(len(segments), 1)
        self.assertWellFormed(segments)
        self.assertEqual(held(segments[0]), list(range(20 - 6, 50 + 6)))   # 6 chunks before and after
        self.assertEqual(returned_at, [50 + 16 - 1])   # returned once 16 silence chunks were heard
        self.assertEqual(segments[0].source, SOURCE_MIC)

    def test_end_is_speech_end_not_when_silence_was_confirmed(self):
        segments, returned_at, _ = run([Q] * 20 + [S] * 30 + [Q] * 30, flush=False)
        end_of_speech = T0 + 50 * CHUNK_SECONDS
        self.assertAlmostEqual(segments[0].end, end_of_speech + 6 * CHUNK_SECONDS, places=9)
        returned_time = T0 + (returned_at[0] + 1) * CHUNK_SECONDS
        self.assertAlmostEqual(returned_time - segments[0].end, (16 - 6) * CHUNK_SECONDS, places=9)

    def test_short_pause_does_not_split(self):
        segments, _, _ = run([Q] * 10 + [S] * 20 + [Q] * 15 + [S] * 20 + [Q] * 30)
        self.assertEqual(len(segments), 1)

    def test_pause_of_min_silence_splits_and_pieces_do_not_overlap(self):
        segments, _, _ = run([Q] * 10 + [S] * 20 + [Q] * 16 + [S] * 20 + [Q] * 30)
        self.assertEqual(len(segments), 2)
        self.assertWellFormed(segments)
        self.assertEqual(held(segments[0])[-1], 29 + 6)     # speech ends at 29, plus padding
        self.assertEqual(held(segments[1])[0], 46 - 6)      # speech starts at 46, minus pre-roll
        # chunks 36-39 are pure silence: in neither segment

    def test_pre_roll_never_takes_audio_the_previous_segment_has(self):
        # pause of 6 chunks = both paddings would want the same chunks; the first segment wins
        segments, _, _ = run([Q] * 10 + [S] * 20 + [Q] * 6 + [S] * 20 + [Q] * 30, min_silence_ms=200)
        self.assertEqual(len(segments), 2)
        self.assertWellFormed(segments)
        self.assertEqual(held(segments[0])[-1] + 1, held(segments[1])[0])

    def test_unsure_does_not_start_a_phrase(self):
        segments, _, _ = run([Q] * 10 + [U] * 100 + [Q] * 30)
        self.assertEqual(segments, [])

    def test_unsure_inside_a_phrase_neither_ends_it_nor_stops_the_wait(self):
        # unsure right after speech: no silence yet, so the phrase stays open
        segments, _, _ = run([Q] * 10 + [S] * 20 + [U] * 40 + [S] * 20 + [Q] * 30)
        self.assertEqual(len(segments), 1)
        # unsure during the wait: the wait goes on (5 silence + 11 unsure = 16 chunks)
        segments, _, _ = run([Q] * 10 + [S] * 20 + [Q] * 5 + [U] * 11 + [S] * 20 + [Q] * 30)
        self.assertEqual(len(segments), 2)

    def test_short_burst_is_dropped_and_counted(self):
        segments, _, segmenter = run([Q] * 10 + [S] * 7 + [Q] * 30 + [S] * 8 + [Q] * 30)
        self.assertEqual(len(segments), 1)                  # 7 chunks dropped, 8 kept
        self.assertEqual(segmenter.dropped_short, 1)
        self.assertEqual(len(held(segments[0])), 6 + 8 + 6)

    def test_dip_before_5_s_does_not_cut(self):
        segments, _, _ = run([Q] * 10 + [S] * 50 + [Q] * 3 + [S] * 50 + [Q] * 30)
        self.assertEqual(len(segments), 1)

    def test_after_5_s_the_first_dip_cuts_at_once_in_its_middle(self):
        # phrase starts at chunk 10 (pre-roll from 4); a dip at 60-62 is too early, the dip at 250-252 cuts
        probs = [Q] * 10 + [S] * 50 + [Q] * 3 + [S] * 187 + [Q] * 3 + [S] * 100 + [Q] * 30
        segments, returned_at, _ = run(probs, flush=False)
        self.assertWellFormed(segments)
        self.assertEqual(len(segments), 2)
        self.assertEqual(held(segments[0]), list(range(4, 251)))   # cut at the dip's middle chunk 251
        self.assertEqual(returned_at[0], 252)                      # as soon as the dip is 3 chunks long
        self.assertEqual(held(segments[1])[0], 251)                # rest of the dip is the next pre-roll
        self.assertEqual(held(segments[1])[-1], 352 + 6)

    def test_two_chunk_dip_does_not_cut(self):
        segments, _, _ = run([Q] * 10 + [S] * 200 + [Q] * 2 + [S] * 50 + [Q] * 30)
        self.assertEqual(len(segments), 1)

    def test_long_speech_without_pause_is_cut_by_10_s(self):
        segments, _, _ = run([Q] * 10 + [S] * 1000 + [Q] * 30)
        self.assertWellFormed(segments)
        self.assertGreater(len(segments), 3)
        for segment in segments[:-1]:
            self.assertGreaterEqual(len(held(segment)), 312 - 31)   # cut within the last second
            self.assertLess(len(held(segment)), 312)
        for first, second in zip(segments, segments[1:]):
            self.assertEqual(held(first)[-1] + 1, held(second)[0])   # nothing lost, nothing twice

    def test_hard_cut_at_the_quietest_chunk_of_the_last_second(self):
        # phrase starts at chunk 10 (pre-roll from 4); 312 chunks are reached at chunk 315,
        # so the last second is chunks 285-315. Chunk 250 is quieter but too far back.
        segments, returned_at, _ = run([Q] * 10 + [S] * 400 + [Q] * 30, quiet={250, 300})
        self.assertWellFormed(segments)
        self.assertEqual(held(segments[0]), list(range(4, 300)))   # ends right before the quiet chunk
        self.assertEqual(returned_at[0], 315)                      # handed over 16 chunks (0.5 s) later
        self.assertEqual(held(segments[1])[0], 300)                # the speech after the cut goes on
        self.assertEqual(held(segments[1])[-1], 409 + 6)           # ...and ends normally

    def test_30_s_of_speech_gives_pieces_no_longer_than_max(self):
        rng = np.random.default_rng(1)
        probs = [Q] * 10 + list(np.where(rng.random(940) < 0.05, Q, S)) + [Q] * 30   # 30 s, tiny gaps
        segments, _, _ = run(probs)
        self.assertWellFormed(segments)
        self.assertGreater(len(segments), 2)
        for segment in segments:
            self.assertLessEqual(segment.end - segment.start, 10.0)

    def test_flush_returns_the_open_phrase(self):
        segments, _, _ = run([Q] * 10 + [S] * 20)
        self.assertEqual(len(segments), 1)
        self.assertEqual(held(segments[0])[-1], 29)   # stream ended: no audio after the speech to add

    def test_wrong_source_and_gaps_raise(self):
        segmenter = Segmenter(SOURCE_MIC)
        chunk = lambda source, start: AudioChunk(source, start, np.zeros(CHUNK_SAMPLES, np.float32))
        with self.assertRaises(ValueError):
            segmenter.feed(chunk(SOURCE_CALL, 0.0))
        segmenter.feed(chunk(SOURCE_MIC, 0.0))
        with self.assertRaises(ValueError):
            segmenter.feed(chunk(SOURCE_MIC, 0.064))      # one chunk missing
        with self.assertRaises(ValueError):
            Segmenter("speaker")
        with self.assertRaises(ValueError):
            Segmenter(SOURCE_MIC, threshold=0.3, neg_threshold=0.4)
        with self.assertRaises(ValueError):
            Segmenter(SOURCE_MIC, quiet_search_ms=6000)           # longer than max - soft (10 - 5 = 5 s)

    def test_real_model_ignores_digital_silence(self):
        segmenter = Segmenter(SOURCE_CALL)
        found = []
        for i in range(int(60 / CHUNK_SECONDS)):          # one minute of zeros
            found += segmenter.feed(AudioChunk(SOURCE_CALL, i * CHUNK_SECONDS, np.zeros(CHUNK_SAMPLES, np.float32)))
        self.assertEqual(found + segmenter.flush(), [])


if __name__ == "__main__":
    unittest.main()
