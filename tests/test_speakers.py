"""Tests for the speakers module's matching logic (briefs/speakers.md), with made-up fingerprints: no model needed.
Run from the repo root:
    python -m unittest tests.test_speakers -v
"""
import unittest

import numpy as np

from transcriber.speakers import SpeakerMatcher

DIM = 192
RNG = np.random.default_rng(0)
VOICES = [RNG.normal(size=DIM) for _ in range(3)]       # random directions: nearly unrelated (cosine ~0)


def phrase(voice: int, noise: float = 0.5, rng=RNG) -> np.ndarray:
    """A fingerprint of one voice: its direction plus noise (cosine to the voice ~0.9 for noise 0.5)."""
    v = VOICES[voice] / np.linalg.norm(VOICES[voice])
    return v + noise * rng.normal(size=DIM) / np.sqrt(DIM)


class SpeakerMatcherTest(unittest.TestCase):

    def test_two_voices_keep_their_labels(self):
        matcher = SpeakerMatcher(threshold=0.5, min_new_s=1.0)
        order = [0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1]
        labels = [matcher.match(phrase(v), 3.0) for v in order]
        self.assertEqual(labels, order)                  # first voice = 0, second = 1, every time
        self.assertEqual(matcher.count, 2)

    def test_labels_follow_first_appearance(self):
        matcher = SpeakerMatcher()
        self.assertEqual([matcher.match(phrase(v), 3.0) for v in (2, 0, 2, 1)], [0, 1, 0, 2])

    def test_third_voice_gets_a_new_label(self):
        matcher = SpeakerMatcher()
        for v in (0, 1, 0, 1):
            matcher.match(phrase(v), 3.0)
        self.assertEqual(matcher.match(phrase(2), 3.0), 2)
        self.assertEqual(matcher.count, 3)

    def test_short_phrase_never_starts_a_speaker(self):
        matcher = SpeakerMatcher(min_new_s=1.0)
        matcher.match(phrase(0), 3.0)
        self.assertEqual(matcher.match(phrase(1), 0.8), 0)    # unlike speaker 0, but too short: closest = 0
        self.assertEqual(matcher.count, 1)
        self.assertEqual(matcher.match(phrase(1), 1.0), 1)    # long enough: new speaker

    def test_short_phrase_never_changes_a_speaker(self):
        a, b = SpeakerMatcher(min_new_s=1.0), SpeakerMatcher(min_new_s=1.0)
        first, probe = phrase(0), phrase(0)
        a.match(first, 3.0)
        b.match(first, 3.0)
        self.assertEqual(a.match(phrase(0, noise=1.0), 0.5), 0)   # a short phrase that matches speaker 0 ...
        self.assertGreaterEqual(a.last_similarity, a.threshold)    # (above the threshold, so it really matched)
        a.match(probe, 3.0)
        b.match(probe, 3.0)
        self.assertAlmostEqual(a.last_similarity, b.last_similarity, places=12)   # ... left its mean unchanged

    def test_short_first_phrase_is_speaker_0_but_founds_nothing(self):
        matcher = SpeakerMatcher(min_new_s=1.0)
        self.assertEqual(matcher.match(phrase(1), 0.4), 0)      # labelled Speaker 1 ...
        self.assertEqual(matcher.count, 0)                      # ... but its weak fingerprint is not kept
        self.assertEqual(matcher.match(phrase(0), 3.0), 0)      # the first long phrase founds speaker 0
        self.assertEqual(matcher.count, 1)
        self.assertEqual(matcher.match(phrase(1), 3.0), 1)      # and only then can a different voice be new

    def test_threshold_decides(self):
        # two fingerprints with a known cosine similarity of 0.6
        x = np.zeros(DIM); x[0] = 1.0
        y = np.zeros(DIM); y[0], y[1] = 0.6, 0.8
        loose, strict = SpeakerMatcher(threshold=0.59), SpeakerMatcher(threshold=0.61)
        for m in (loose, strict):
            m.match(x, 3.0)
        self.assertEqual(loose.match(y, 3.0), 0)
        self.assertEqual(strict.match(y, 3.0), 1)
        self.assertAlmostEqual(loose.last_similarity, 0.6, places=12)

    def test_similarity_is_to_the_mean_direction_not_the_sum(self):
        # speaker 0 heard 3 times: its sum is 3 x long; a phrase with cosine 0.4 must still score 0.4
        x = np.zeros(DIM); x[0] = 1.0
        y = np.zeros(DIM); y[0], y[1] = 0.4, np.sqrt(1 - 0.4 ** 2)
        matcher = SpeakerMatcher(threshold=0.5)
        for _ in range(3):
            matcher.match(x, 3.0)
        self.assertEqual(matcher.match(y, 3.0), 1)
        self.assertAlmostEqual(matcher.last_similarity, 0.4, places=12)

    def test_length_of_the_fingerprint_does_not_matter(self):
        a, b = SpeakerMatcher(), SpeakerMatcher()
        stream = [phrase(v) for v in (0, 1, 0, 1, 1, 0)]
        self.assertEqual([a.match(e, 3.0) for e in stream], [b.match(7.5 * e, 3.0) for e in stream])

    def test_mean_direction_follows_the_speaker(self):
        # a voice that drifts slowly (e.g. louder, closer to the mic) is still followed by its running mean
        # far enough that the last phrase would no longer match the first one alone (checked: without updating the
        # mean, this stream splits into two speakers)
        matcher = SpeakerMatcher(threshold=0.7)
        base, other = VOICES[0] / np.linalg.norm(VOICES[0]), VOICES[1] / np.linalg.norm(VOICES[1])
        labels = [matcher.match(base * (1 - t) + other * t, 3.0) for t in np.linspace(0, 0.8, 21)]
        self.assertEqual(labels, [0] * 21)

    def test_bad_input_raises(self):
        matcher = SpeakerMatcher()
        for bad in (np.zeros(DIM), np.full(DIM, np.nan), np.ones((2, DIM)), [1.0, 2.0]):
            with self.assertRaises(ValueError):
                matcher.match(bad, 3.0)
        matcher.match(phrase(0), 3.0)
        with self.assertRaises(ValueError):
            matcher.match(np.ones(DIM + 1), 3.0)               # a different model's fingerprint
        for args in ((1.0, 1.0), (-1.0, 1.0), (0.5, -1.0)):
            with self.assertRaises(ValueError):
                SpeakerMatcher(*args)


if __name__ == "__main__":
    unittest.main()
