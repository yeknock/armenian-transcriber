"""Speakers module: label call-side segments "Speaker 1", "Speaker 2", ... (D4).

Two parts, so the labelling logic can be tested without the model:
- SpeakerMatcher: online clustering of voice fingerprints (embeddings), pure numpy. Every speaker keeps the mean
  direction of their fingerprints; a phrase joins the most similar speaker if the cosine similarity reaches
  `threshold`, otherwise it starts a new speaker, but only if it is at least `min_new_s` long (a short phrase gives a
  weak fingerprint). Short phrases never start a speaker and never change one: they take the most similar label.
- _TitaNet: NVIDIA TitaNet-Large (nvidia/speakerverification_en_titanet_large, 23M parameters, 192 numbers per phrase,
  16 kHz mono; model card: 0.66 % EER on VoxCeleb1, CC-BY-4.0), run with the NeMo toolkit the ASR already uses, on
  the CPU. Loaded from the git-ignored models/ folder only, so nothing is fetched at run time.
SpeakerIdentifier puts them together: identify(audio) -> "Speaker N".
Contract, tests and done-criteria: briefs/speakers.md
"""
from pathlib import Path

import numpy as np

from transcriber.contracts import SAMPLE_RATE

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "titanet_large"
DOWNLOAD = "hf download nvidia/speakerverification_en_titanet_large --local-dir models/titanet_large"
MIN_SECONDS = 0.3     # shorter input means something upstream is broken (the VAD gives >= 0.6 s)


class SpeakerMatcher:
    """Labels a stream of fingerprints with speaker numbers 0, 1, 2, ... in order of first appearance.

    threshold: the lowest cosine similarity to a speaker's mean fingerprint that still counts as that speaker.
    min_new_s: phrases shorter than this never start a new speaker and never change a speaker's mean (weak
    fingerprints); they get the most similar speaker. Before any speaker exists, a short phrase is labelled 0 but stores
    nothing: the first phrase of min_new_s or more founds speaker 0.
    Defaults measured on the 2-voice podcast (D4): phrases >= 2 s match their own speaker at >= 0.66 and the other at
    <= 0.35, so 0.45 leaves a margin both ways; phrases < 2 s matched their own speaker as low as 0.04.
    """

    def __init__(self, threshold: float = 0.45, min_new_s: float = 2.0) -> None:
        if not -1.0 < threshold < 1.0 or min_new_s < 0:
            raise ValueError(f"need -1 < threshold < 1 and min_new_s >= 0, got {threshold}, {min_new_s}")
        self.threshold, self.min_new_s = threshold, min_new_s
        self._sums: list[np.ndarray] = []      # per speaker: sum of unit-length fingerprints (its mean direction)
        self.last_similarity: float | None = None   # best similarity of the last phrase (for scripts and logs)

    @property
    def count(self) -> int:
        return len(self._sums)

    def match(self, embedding: np.ndarray, seconds: float) -> int:
        """embedding: 1-D, finite, not all zeros; seconds: length of the phrase. Returns the speaker number."""
        if not isinstance(embedding, np.ndarray) or embedding.ndim != 1 or not np.isfinite(embedding).all():
            raise ValueError("embedding must be a finite 1-D numpy array")
        norm = float(np.linalg.norm(embedding))
        if norm == 0.0:
            raise ValueError("embedding is all zeros")
        unit = embedding.astype(np.float64) / norm
        long_enough = seconds >= self.min_new_s
        if not self._sums:
            if long_enough:                    # a short first phrase gets label 0 but founds nothing (weak fingerprint)
                self._sums.append(unit.copy())
            self.last_similarity = None
            return 0
        if unit.shape != self._sums[0].shape:
            raise ValueError(f"embedding has {unit.shape[0]} numbers, earlier ones had {self._sums[0].shape[0]}")
        similarities = [float(unit @ (s / np.linalg.norm(s))) for s in self._sums]
        best = int(np.argmax(similarities))
        self.last_similarity = similarities[best]
        if similarities[best] >= self.threshold:
            if long_enough:
                self._sums[best] += unit
            return best
        if long_enough:
            self._sums.append(unit.copy())
            return len(self._sums) - 1
        return best                            # short and unlike everyone: closest speaker, nothing changes


class _TitaNet:
    """TitaNet-Large through NeMo on the CPU: one phrase in, one unit-length 192-number fingerprint out."""

    def __init__(self) -> None:
        found = sorted(MODEL_DIR.glob("*.nemo"))
        if len(found) != 1:
            raise FileNotFoundError(f"need exactly one .nemo file in {MODEL_DIR}, found {len(found)}. "
                                    f"Get it with:\n  {DOWNLOAD}")
        from nemo.collections.asr.models import EncDecSpeakerLabelModel
        from nemo.utils import logging as nemo_logging
        nemo_logging.setLevel(nemo_logging.ERROR)
        # torch's thread count is process-wide and set by Transcriber (briefs/asr.md contract question 1): not here.
        self._model = EncDecSpeakerLabelModel.restore_from(str(found[0]), map_location="cpu")
        self._model.eval()
        # Warm-up: the first run is slower; quiet noise, not zeros (all zeros has no direction to measure).
        self.embed(np.random.default_rng(0).normal(0, 0.01, SAMPLE_RATE).astype(np.float32))

    def embed(self, audio: np.ndarray) -> np.ndarray:
        # infer_segment (NeMo 3.0.0 label_models.py) copies the array (np.array([segment])) and runs under no_grad.
        embedding, _ = self._model.infer_segment(audio)
        vector = embedding.detach().cpu().numpy().reshape(-1).astype(np.float32)
        if vector.shape != (192,) or not np.isfinite(vector).all():
            raise RuntimeError(f"TitaNet returned {vector.shape} / non-finite values, expected 192 numbers")
        return vector / np.linalg.norm(vector)


class SpeakerIdentifier:
    """One instance per session; labels stay stable for the whole session.
    Never returns "Me": the pipeline labels the mic side itself.
    """

    def __init__(self, threshold: float = 0.45, min_new_s: float = 2.0) -> None:
        """Load TitaNet once (slow); raise if it cannot be loaded. Tuning: see SpeakerMatcher (D4)."""
        self._matcher = SpeakerMatcher(threshold=threshold, min_new_s=min_new_s)
        self._model = _TitaNet()

    @property
    def speakers_found(self) -> int:
        """How many call-side speakers this session has seen so far."""
        return self._matcher.count

    def embed(self, audio: np.ndarray) -> np.ndarray:
        """The phrase's unit-length fingerprint (192 numbers). For scripts/try_speakers.py; identify() uses it."""
        if not isinstance(audio, np.ndarray) or audio.dtype != np.float32 or audio.ndim != 1:
            raise ValueError("audio must be a 1-D float32 array")
        if len(audio) < MIN_SECONDS * SAMPLE_RATE or not np.isfinite(audio).all():
            raise ValueError(f"audio must be finite and at least {MIN_SECONDS} s long")
        return self._model.embed(audio)

    def identify(self, audio: np.ndarray) -> str:
        """audio: float32, mono, 16 kHz, one call-side segment.

        Always returns "Speaker N" (N = 1, 2, ... in order of first appearance).
        Called from a single thread.
        """
        return f"Speaker {self._matcher.match(self.embed(audio), len(audio) / SAMPLE_RATE) + 1}"
