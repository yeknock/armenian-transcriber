"""MT module: Armenian text -> English text (NLLB-200 distilled, hye_Armn -> eng_Latn, D3).

Runs locally with CTranslate2 (int8, CPU). The model is converted once from Meta's original checkpoint into the
git-ignored models/ folder (command in the error message when it is missing) and loaded from there only, so
nothing is fetched at run time. Each segment is split into sentences, the sentences are translated together in
one batch, and the English sentences are joined in order, so no sentence can be dropped.
Contract, tests and done-criteria: briefs/mt.md
"""
import re
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
SRC_LANG, TGT_LANG = "hye_Armn", "eng_Latn"

# name -> (folder in models/, Hugging Face id of Meta's original checkpoint)
MODELS = {
    "nllb-600m": ("nllb_600m_ct2_int8", "facebook/nllb-200-distilled-600M"),
    "nllb-1.3b": ("nllb_1.3b_ct2_int8", "facebook/nllb-200-distilled-1.3B"),
}

# A sentence ends at the Armenian full stop ։ (also without a space after it: it never occurs inside numbers or
# abbreviations), or at an ASCII full stop / colon (often typed for the Armenian one), ! ? or an ellipsis followed
# by a space. The Armenian question and exclamation marks (՞ ՜) sit on a vowel inside the word, so they do not end
# a sentence. "3.5" is not split (no space after the dot).
_SENTENCE_END = re.compile(r"(?<=։)\s*(?=\S)|(?<=[.:!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """'Բարեւ։ Ինչպե՞ս ես։' -> ['Բարեւ։', 'Ինչպե՞ս ես։']; text without an end mark is one sentence.
    A piece without letters or digits (e.g. a doubled '։։') is never translated alone (NLLB would invent a word):
    it is attached to the sentence before it, or left out when no sentence came before (it holds no words)."""
    sentences: list[str] = []
    for part in (p.strip() for p in _SENTENCE_END.split(text.strip())):
        if any(ch.isalnum() for ch in part):
            sentences.append(part)
        elif part and sentences:
            sentences[-1] += part
    return sentences


def convert_command(name: str) -> str:
    folder, hf_id = MODELS[name]
    # --low_cpu_mem_usage: the 1.3B original is ~5.5 GB in float32; loading it the normal way can exhaust 8 GB.
    return (f"ct2-transformers-converter --model {hf_id} --output_dir models/{folder} --quantization int8 "
            "--low_cpu_mem_usage "
            "--copy_files tokenizer.json tokenizer_config.json special_tokens_map.json sentencepiece.bpe.model")


class Translator:
    def __init__(self, model: str = "nllb-600m", beam_size: int = 2, threads: int = 4) -> None:
        """Load the model once. If model files are missing, raise with a message saying how
        to download/convert them. No network after the first download.

        model: one of MODELS (D3a: 600M vs 1.3B). beam_size: 1 = greedy (fastest); more = better English,
        slower. threads: CPU threads for CTranslate2.
        """
        if model not in MODELS:
            raise ValueError(f"model must be one of {list(MODELS)}, got {model!r}")
        if beam_size < 1 or threads < 1:
            raise ValueError(f"beam_size and threads must be >= 1, got {beam_size}, {threads}")
        folder = MODELS_DIR / MODELS[model][0]
        if not (folder / "model.bin").is_file() or not (folder / "tokenizer.json").is_file():
            raise FileNotFoundError(f"translation model {folder} not found or incomplete. Convert it once "
                                    f"(needs the internet and ~3-6 GB of temporary download):\n  {convert_command(model)}")
        import ctranslate2
        from transformers import AutoTokenizer
        self._translator = ctranslate2.Translator(str(folder), device="cpu", compute_type="int8",
                                                  inter_threads=1, intra_threads=threads)
        self._tokenizer = AutoTokenizer.from_pretrained(folder, src_lang=SRC_LANG)
        if self._tokenizer.convert_tokens_to_ids(TGT_LANG) == self._tokenizer.unk_token_id:
            raise RuntimeError(f"{folder}: the tokenizer does not know the language code {TGT_LANG!r}")
        self.model, self.beam_size, self.threads = model, beam_size, threads
        self.translate("Բարեւ։")   # warm-up: the first call is slower, so it happens here, not on the first phrase

    def translate(self, hy_text: str) -> str:
        """One segment of Armenian text (may hold several sentences) -> English text.

        Every sentence must appear in the output. "" -> "". Called from a single worker thread.
        """
        if not isinstance(hy_text, str):
            raise TypeError(f"hy_text must be a str, got {type(hy_text).__name__}")
        sentences = split_sentences(hy_text)
        if not sentences:
            return ""
        sources = [self._tokenizer.convert_ids_to_tokens(self._tokenizer.encode(s)) for s in sentences]
        results = self._translator.translate_batch(
            sources, target_prefix=[[TGT_LANG]] * len(sources), beam_size=self.beam_size,
            # an English sentence is about as long as its Armenian source; the cap stops a repetition loop
            max_decoding_length=min(256, 2 * max(len(s) for s in sources) + 10))
        english = []
        for result in results:
            tokens = result.hypotheses[0][1:]          # drop the target-language tag
            english.append(self._tokenizer.decode(self._tokenizer.convert_tokens_to_ids(tokens),
                                                  skip_special_tokens=True).strip())
        return " ".join(english)
