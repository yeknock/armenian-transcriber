"""Text normalisation and CER / WER for Armenian (briefs/eval.md). Uses jiwer 4.

normalize() is applied to the reference and to the ASR output before scoring, so only the words count:
- lower case (casefold);
- the marks written ON a word are removed: ՞ (question), ՜ (exclamation), ՛ (emphasis), ՚ (apostrophe), and the ASCII
  apostrophe ', so «ինչպե՞ս» and «ինչպես» are the same word;
- every other punctuation mark is replaced by a space: ։ ՝ « » , . : ; ! ? … — - ( ) " and the like. A space, not
  nothing, because the reference and the ASR do not always put a space after a mark («տեսախցիկ։Ու»);
- «և» is written «եւ» (the ASR writes եւ, people type և);
- runs of whitespace become one space.
Digits stay as they are: «33» and «երեսուներեք» are different words, and that counts as an error.

CER = character edits / reference characters (spaces count as characters); WER = word edits / reference words.
Both are computed over all given pairs together (corpus level), not as an average of per-file rates.
"""
import re

import jiwer

_ON_WORD = "՞՜՛՚'"
_ON_WORD_RE = re.compile(f"[{re.escape(_ON_WORD)}]")
_SPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """«Բարև, ինչպե՞ս ես։Լավ» -> 'բարեւ ինչպես ես լավ'."""
    text = _ON_WORD_RE.sub("", text.casefold()).replace("և", "եւ")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return _SPACE_RE.sub(" ", text).strip()


def _pairs(references: list[str], hypotheses: list[str]) -> tuple[list[str], list[str]]:
    if len(references) != len(hypotheses) or not references:
        raise ValueError(f"need the same, non-zero number of references and hypotheses, got "
                         f"{len(references)} and {len(hypotheses)}")
    refs = [normalize(r) for r in references]
    if not all(refs):
        raise ValueError("a reference is empty after normalisation")
    return refs, [normalize(h) for h in hypotheses]


def cer(references: list[str], hypotheses: list[str]) -> float:
    refs, hyps = _pairs(references, hypotheses)
    return jiwer.process_characters(refs, hyps).cer


def wer(references: list[str], hypotheses: list[str]) -> float:
    refs, hyps = _pairs(references, hypotheses)
    return jiwer.process_words(refs, hyps).wer


def word_alignment(reference: str, hypothesis: str) -> str:
    """jiwer's word-by-word alignment of one normalised pair (S = substituted, D = deleted, I = inserted)."""
    refs, hyps = _pairs([reference], [hypothesis])
    return jiwer.visualize_alignment(jiwer.process_words(refs, hyps), show_measures=False)
