"""ASR module: Armenian speech -> Armenian text (nvidia/stt_hy_fastconformer_hybrid_large_pc, D1).

NVIDIA's original .nemo checkpoint, run with the NeMo toolkit on the CPU, RNNT (Transducer) head (D1a).
The checkpoint lives in the git-ignored models/ folder and is loaded from there only, so nothing is fetched
at run time. Contract, tests and done-criteria: briefs/asr.md
"""
import copy
from pathlib import Path

import numpy as np

from transcriber.contracts import SAMPLE_RATE

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "nvidia_hy_nemo"
DOWNLOAD = "hf download nvidia/stt_hy_fastconformer_hybrid_large_pc --local-dir models/nvidia_hy_nemo"

MIN_SECONDS = 0.1    # shorter input means something upstream is broken (VAD gives >= 0.6 s)
MAX_SECONDS = 20.0   # contract: <= 15 s; the model was trained on clips of 0.1-20 s (its model_config.yaml)


class Transcriber:
    def __init__(self, threads: int = 4, beam_size: int = 1) -> None:
        """Load the model once (slow). Raise if it cannot be loaded. No network after the first download.

        threads: CPU threads for torch (the M1 has 4 performance cores). Note: torch's thread count is
        process-wide, so this also applies to every other torch model in the program.
        beam_size: 1 = greedy RNNT decoding (D1a, the default). > 1 = RNNT beam search with NeMo's `malsd_batch`
        strategy (the one NeMo recommends; read in NeMo 3.0.0 rnnt_decoding.py), keeping beam_size candidates.
        """
        if threads < 1 or beam_size < 1:
            raise ValueError(f"threads and beam_size must be >= 1, got {threads}, {beam_size}")
        found = sorted(MODEL_DIR.glob("*.nemo"))
        if len(found) != 1:
            raise FileNotFoundError(f"need exactly one .nemo file in {MODEL_DIR}, found {len(found)}. "
                                    f"Get it with:\n  {DOWNLOAD}")
        import torch
        from nemo.collections.asr.models import EncDecHybridRNNTCTCBPEModel
        from nemo.utils import logging as nemo_logging
        from omegaconf import open_dict
        nemo_logging.setLevel(nemo_logging.ERROR)
        torch.set_num_threads(threads)
        self._torch = torch
        self._model = EncDecHybridRNNTCTCBPEModel.restore_from(str(found[0]), map_location="cpu")
        self._model.eval()                                # eval mode: no dither, no dropout -> deterministic
        decoding = None                                   # greedy: the checkpoint's own decoding settings
        if beam_size > 1:
            decoding = copy.deepcopy(self._model.cfg.decoding)
            with open_dict(decoding):
                decoding.strategy = "malsd_batch"
                decoding.beam.beam_size = beam_size
                # The checkpoint stores false here: NeMo would then return every candidate, not the best text.
                decoding.beam.return_best_hypothesis = True
                decoding.beam.allow_cuda_graphs = False   # a GPU feature; we run on the CPU
        self._model.change_decoding_strategy(decoding_cfg=decoding, decoder_type="rnnt", verbose=False)
        self.threads, self.beam_size = threads, beam_size
        # Warm-up: the first run is slower (memory allocation), so do it here, not on the first phrase.
        self._run(np.zeros(SAMPLE_RATE, dtype=np.float32))

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32, mono, 16 kHz, about 0.3-15 s; not modified.

        Return Armenian text with punctuation; "" only when the model outputs nothing.
        Called from a single worker thread.
        """
        if not isinstance(audio, np.ndarray) or audio.dtype != np.float32 or audio.ndim != 1:
            found = (f"{audio.dtype} array with shape {audio.shape}" if isinstance(audio, np.ndarray)
                     else type(audio).__name__)
            raise ValueError(f"audio must be a 1-D float32 array, got {found}")
        seconds = len(audio) / SAMPLE_RATE
        if not MIN_SECONDS <= seconds <= MAX_SECONDS:
            raise ValueError(f"audio is {seconds:.2f} s; expected {MIN_SECONDS}-{MAX_SECONDS} s")
        if not np.isfinite(audio).all():
            raise ValueError("audio contains NaN or inf")
        return self._run(audio).strip()

    def _run(self, audio: np.ndarray) -> str:
        # NeMo wraps the array with torch.as_tensor (shared memory), so it gets a copy: the input stays untouched.
        with self._torch.inference_mode():
            result = self._model.transcribe([audio.copy()], batch_size=1, verbose=False)
        # A list of str or Hypothesis; hybrid models may wrap it in a (best, all) tuple.
        if isinstance(result, tuple):
            result = result[0]
        if not isinstance(result, list) or len(result) != 1:
            raise RuntimeError(f"NeMo transcribe() returned {type(result).__name__}, expected a list with one item")
        item = result[0]
        text = item.text if hasattr(item, "text") else item
        if not isinstance(text, str):
            raise RuntimeError(f"NeMo transcribe() returned a {type(item).__name__} without text")
        return text
