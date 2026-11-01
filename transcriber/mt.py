"""MT module: Armenian text -> English text (NLLB-200 distilled, hye_Armn -> eng_Latn, D3).

Runs locally with CTranslate2 (int8, CPU). The model is converted once from Meta's original checkpoint into the
git-ignored models/ folder (command in the error message when it is missing) and loaded from there only, so
nothing is fetched at run time. Each segment is split into sentences (one-word sentences stay with a neighbour,
see make_pieces), the pieces are translated together in one batch, and the English pieces are joined in order, so
no sentence is left out. Two exceptions, both because NLLB invents English for one-word input (D3b):
- the ASR's text for coughs, "hmm" and breaths (is_non_speech) gets no English; the pipeline does not print it;
- a segment that is just one common reply word (Այո, Հա, Ոչ, ...) is taken from the small ONE_WORD glossary.
Contract, tests and done-criteria: briefs/mt.md
"""
import re
from dataclasses import dataclass
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


# One-word segments NLLB-600M gets wrong alone (eval/mt_short.txt: «Այո։» -> "I did.", «Ալո։» -> "I'm going to be a
# little late."). Used only when the whole segment is that one word; keys as written by normalize_word().
ONE_WORD = {
    "այո": "Yes.", "հա": "Yeah.", "ոչ": "No.", "չէ": "No.", "լավ": "Okay.", "իհարկե": "Of course.",
    "մերսի": "Thanks.", "շնորհակալություն": "Thank you.", "ներողություն": "Sorry.", "ալո": "Hello?",
    "բարեւ": "Hi.", "ցտեսություն": "Goodbye.", "հաջողություն": "Good luck.", "ճիշտ": "Right.",
    "հասկացա": "Got it.", "գիտեմ": "I know.", "օքեյ": "Okay.", "ինչ": "What?",
}
# What the ASR wrote for coughs, "hmm" and breaths in the live calls (44 of 268 phrases, both sides; D3b), after
# normalize_word(). A segment is also non-speech when none of its words has two letters (Հ։, Ա։, ։).
NON_SPEECH_WORDS = {"հովհ", "ովհ"}


def normalize_word(word: str) -> str:
    """Letters only, lower case, և written as եւ (the ASR's spelling): «Այո։» -> 'այո', 'Ի՞նչ' -> 'ինչ'."""
    return "".join(ch for ch in word.casefold() if ch.isalpha()).replace("և", "եւ")


def is_non_speech(text: str) -> bool:
    """True for the ASR's text for a cough, "hmm" or breath (Հովհ., Հ։, a single letter, only punctuation).
    The pipeline skips such segments; translate() gives "" for them."""
    if any(ch.isdigit() for ch in text):          # a number is speech ("5" as an answer)
        return False
    words = [normalize_word(w) for w in text.split()]
    words = [w for w in words if w]
    return all(len(w) < 2 for w in words) or all(w in NON_SPEECH_WORDS for w in words)


@dataclass(frozen=True)
class Piece:
    """How one part of a segment was translated (Translator.translate_detailed)."""
    hy: str
    en: str
    how: str              # "nllb", "glossary" or "non-speech"
    score: float | None   # NLLB only: mean log-probability per output token (0 = sure, more negative = less sure)


def make_pieces(text: str) -> list[str]:
    """The pieces translate() sends to NLLB: the sentences of split_sentences(), except that a one-word sentence is
    joined to the next sentence (or to the one before, if it is the last).

    Why (chat 06, eval/mt_short.txt): alone, a one-word sentence gets invented English («Հաջողություն։» -> "What is
    the meaning of life?", «Այո։» -> "I did."); next to its neighbour it comes out right ("... tomorrow. Good luck.",
    "Yes. I will be there tomorrow."), and NLLB kept every sentence in all 4 such tests. Longer sentences stay apart:
    given two long sentences at once, NLLB dropped one of them.
    """
    pieces: list[str] = []
    waiting = ""                    # one-word sentences not yet attached to a longer one
    for sentence in split_sentences(text):
        joined = f"{waiting} {sentence}" if waiting else sentence
        if len(sentence.split()) == 1:
            waiting = joined
        else:
            pieces.append(joined)
            waiting = ""
    if waiting:
        if pieces:
            pieces[-1] += " " + waiting
        else:
            pieces.append(waiting)
    return pieces


def convert_command(name: str) -> str:
    folder, hf_id = MODELS[name]
    # --low_cpu_mem_usage: the 1.3B original is ~5.5 GB in float32; loading it the normal way can exhaust 8 GB.
    return (f"ct2-transformers-converter --model {hf_id} --output_dir models/{folder} --quantization int8 "
            "--low_cpu_mem_usage "
            "--copy_files tokenizer.json tokenizer_config.json special_tokens_map.json sentencepiece.bpe.model")


class Translator:
    def __init__(self, model: str = "nllb-600m", beam_size: int = 1, threads: int = 4) -> None:
        """Load the model once. If model files are missing, raise with a message saying how
        to download/convert them. No network after the first download.

        model: one of MODELS (D3a: 600M). beam_size: 1 = greedy (D3a: rated as good as beam 2 on our lines and
        23 % faster). threads: CPU threads for CTranslate2.
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
        # NLLB expects [hye_Armn, ...pieces..., </s>] (CTranslate2 NLLB recipe). Older transformers versions put the
        # language code at the end instead ("legacy behaviour"); that still runs but translates worse, so check it.
        probe = self._tokenizer.convert_ids_to_tokens(self._tokenizer.encode("Բարեւ"))
        if probe[0] != SRC_LANG or probe[-1] != self._tokenizer.eos_token or len(probe) < 3:
            raise RuntimeError(f"{folder}: the tokenizer gives {probe}; expected [{SRC_LANG!r}, ..., "
                               f"{self._tokenizer.eos_token!r}]")
        self.model, self.beam_size, self.threads = model, beam_size, threads
        # warm-up through NLLB itself (not the glossary): the first call is slower, so it happens here
        self.translate_pieces(["Բարեւ, ինչպե՞ս ես։"])

    def translate(self, hy_text: str) -> str:
        """One segment of Armenian text (may hold several sentences) -> English text.

        Every sentence must appear in the output. "" -> "". Non-speech (is_non_speech) -> "".
        Called from a single worker thread.
        """
        return " ".join(piece.en for piece in self.translate_detailed(hy_text) if piece.en)

    def translate_detailed(self, hy_text: str) -> list[Piece]:
        """The same work as translate(), with how each piece was translated (for scripts/try_mt.py and logs)."""
        if not isinstance(hy_text, str):
            raise TypeError(f"hy_text must be a str, got {type(hy_text).__name__}")
        pieces = make_pieces(hy_text)
        if not pieces:
            return []
        if is_non_speech(hy_text):
            return [Piece(hy_text.strip(), "", "non-speech", None)]
        words = hy_text.split()
        if len(words) == 1 and normalize_word(words[0]) in ONE_WORD:
            return [Piece(words[0], ONE_WORD[normalize_word(words[0])], "glossary", None)]
        return [Piece(hy, en, "nllb", score) for hy, (en, score) in zip(pieces, self.translate_pieces(pieces))]

    def translate_pieces(self, pieces: list[str]) -> list[tuple[str, float]]:
        """Lower level, no sentence splitting: translate each piece as it is, in one batch.

        Returns (English, score) per piece, in order. score = CTranslate2's mean log-probability per output token
        (0 = sure; more negative = less sure). translate() uses this; scripts/try_mt.py uses it to compare
        splitting with whole segments and to look at the scores.
        """
        if not pieces or not all(isinstance(p, str) and p.strip() for p in pieces):
            raise ValueError(f"pieces must be a non-empty list of non-empty strings, got {pieces!r}")
        sources = [self._tokenizer.convert_ids_to_tokens(self._tokenizer.encode(p)) for p in pieces]
        results = self._translator.translate_batch(
            sources, target_prefix=[[TGT_LANG]] * len(sources), beam_size=self.beam_size, return_scores=True,
            # an English sentence is about as long as its Armenian source; the cap stops a repetition loop
            max_decoding_length=min(256, 2 * max(len(s) for s in sources) + 10))
        out = []
        for result in results:
            tokens = result.hypotheses[0][1:]          # drop the target-language tag
            english = self._tokenizer.decode(self._tokenizer.convert_tokens_to_ids(tokens), skip_special_tokens=True)
            out.append((english.strip(), result.scores[0]))
        return out
