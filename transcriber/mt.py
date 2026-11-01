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
# little late."). Used only when the whole segment is that one word; keys as written by lookup_key(). A word with ՞
# gets a question mark: «Այո՞» -> "Yes?". First 18 entries D3b; the rest added in chat 06 (user's request), D3d.
ONE_WORD = {
    # yes / no / okay
    "այո": "Yes.", "հա": "Yeah.", "ըհը": "Uh-huh.", "մհմ": "Mm-hmm.", "ոչ": "No.", "չէ": "No.", "լավ": "Okay.",
    "օքեյ": "Okay.", "օկեյ": "Okay.", "օկ": "OK.", "նորմալ": "Fine.", "ճիշտ": "Right.", "իհարկե": "Of course.",
    "անպայման": "Definitely.", "հաստատ": "For sure.", "համաձայն": "Agreed.", "լրիվ": "Totally.",
    "գուցե": "Maybe.", "միգուցե": "Maybe.", "երեւի": "Probably.", "իսկապես": "Really.", "իրոք": "Really.",
    # understanding
    "հասկացա": "Got it.", "հասկանալի": "Understood.", "պարզ": "Clear.", "գիտեմ": "I know.",
    "չգիտեմ": "I don't know.",
    # politeness, greetings
    "մերսի": "Thanks.", "շնորհակալ": "Thanks.", "շնորհակալություն": "Thank you.", "խնդրեմ": "You're welcome.",
    "ոչինչ": "That's okay.", "ներողություն": "Sorry.", "կներես": "Sorry.", "կներեք": "Sorry.",
    "ներեցեք": "Excuse me.", "ապրես": "Well done.", "ալո": "Hello?", "բարեւ": "Hi.", "բարեւձեզ": "Hello.",
    "ողջույն": "Hello.", "ցտեսություն": "Goodbye.", "հաջող": "Bye.", "առայժմ": "Bye for now.",
    "հաջողություն": "Good luck.", "սպասի": "Wait.", "սպասիր": "Wait.", "սպասեք": "Wait.",
    # question words said alone
    "ինչ": "What?", "հը": "Huh?", "ինչու": "Why?", "ինչպես": "How?", "ոնց": "How?", "որտեղ": "Where?",
    "երբ": "When?", "ով": "Who?", "ինչքան": "How much?",
    # discourse words said alone
    "բայց": "But...", "դե": "Well.", "ուրեմն": "So.",
}
# What the ASR wrote for coughs, "hmm" and breaths in the live calls (44 of 268 phrases, both sides; D3b), plus
# hesitation sounds (chat 06), as written by lookup_key(). A segment is also non-speech when none of its words has two
# different letters: Հ։, Ա։, ։, and stretched sounds like «ըըը», «մմմ» (lookup_key collapses repeated letters).
NON_SPEECH_WORDS = {"հովհ", "ովհ", "հմ", "ըմ", "հըմ"}


def normalize_word(word: str) -> str:
    """Letters only, lower case, և written as եւ (the ASR's spelling): «Այո։» -> 'այո', 'Ի՞նչ' -> 'ինչ'."""
    return "".join(ch for ch in word.casefold() if ch.isalpha()).replace("և", "եւ")


def lookup_key(word: str) -> str:
    """normalize_word() with repeated letters collapsed, for the glossary and the non-speech check only:
    «Հաաա» -> 'հա', «ըըը» -> 'ը', «Այոո՞» -> 'այո'."""
    return re.sub(r"(.)\1+", r"\1", normalize_word(word))


def is_non_speech(text: str) -> bool:
    """True for the ASR's text for a cough, "hmm" or breath (Հովհ., Հ։, «ըըը», a single letter, only punctuation).
    The pipeline skips such segments; translate() gives "" for them."""
    if any(ch.isdigit() for ch in text):          # a number is speech ("5" as an answer)
        return False
    words = [lookup_key(w) for w in text.split()]
    words = [w for w in words if w]
    return all(len(w) < 2 or w in NON_SPEECH_WORDS for w in words)     # «Հ. Հմ։» mixes both kinds


def one_word_english(text: str) -> str | None:
    """The glossary English for a segment that is one ONE_WORD word, else None. «Այո՞» -> "Yes?"."""
    words = text.split()
    if len(words) != 1 or lookup_key(words[0]) not in ONE_WORD:
        return None
    english = ONE_WORD[lookup_key(words[0])]
    return english.rstrip(".!?") + "?" if "՞" in words[0] else english


@dataclass(frozen=True)
class Piece:
    """How one part of a segment was translated (Translator.translate_detailed)."""
    hy: str
    en: str
    how: str              # "nllb", "glossary" or "non-speech"
    score: float | None   # NLLB only: mean log-probability per output token (0 = sure, more negative = less sure)
    nllb_input: str | None = None   # NLLB only: the text NLLB got, when to_written() changed it


# Spoken Armenian -> written forms, for NLLB's input only (the HY line keeps the ASR text). NLLB learned mostly written
# Armenian and mistranslates spoken forms (live call 2026-11-01: «ջահել ժամանակ» "in the Holocaust", «վաբշ» "you
# bastard"). First chosen from the forms in 421 real ASR phrases, then widened with common spoken forms (chat 06).
# Left out on purpose, because a spoken and a written meaning collide: իրան (Iran), արա (do!), մենակ (alone),
# կանգնի / սպասի (subjunctive), ինչի (of what; only «ինչի՞» = why), էլի (again), հլը, բա, տո, դզում (needs reordering).
# Keys: lower case, without ՞ ՜ ՛. D3d.
SPOKEN_TO_WRITTEN = {
    # copula «ա» = «է», also stuck to the word before
    "ա": "է", "պետքա": "պետք է", "լավա": "լավ է", "ինչա": "ինչ է",
    # this / that / there / so (է- for այ-), and their spoken variants
    "էս": "այս", "էդ": "այդ", "էտ": "այդ", "էն": "այն",
    "էստեղ": "այստեղ", "ստեղ": "այստեղ", "էդտեղ": "այդտեղ", "էնտեղ": "այնտեղ",
    "էսպես": "այսպես", "էդպես": "այդպես", "էնպես": "այնպես",
    "էսքան": "այսքան", "էդքան": "այդքան", "էնքան": "այնքան", "էսօր": "այսօր",
    "էսի": "սա", "էդի": "դա", "էտի": "դա", "էնի": "այն",
    "սենց": "այսպես", "ըսենց": "այսպես", "տենց": "այդպես", "ըտենց": "այդպես", "նենց": "այնպես",
    "ընենց": "այնպես", "ոնց": "ինչպես",
    # own / they
    "իրա": "իր", "իրանց": "իրենց",
    # can (spoken կարա- for կարող)
    "կարում": "կարող", "կարա": "կարող", "կարամ": "կարող եմ", "կարաս": "կարող ես", "կարանք": "կարող ենք",
    "կարաք": "կարող եք", "կարան": "կարող են",
    # know (spoken -դ- for -տ-)
    "գիդեմ": "գիտեմ", "չգիդեմ": "չգիտեմ", "գիդես": "գիտես", "գիդի": "գիտի",
    # spoken է- for ե- at the start of a word
    "էրեխա": "երեխա", "էրեխեք": "երեխաներ", "էրկու": "երկու", "էրեք": "երեք", "էրեկ": "երեկ", "էրբ": "երբ",
    "էրկար": "երկար", "էկել": "եկել", "էկա": "եկա", "էկավ": "եկավ", "էկար": "եկար", "էկեք": "եկեք",
    "էղել": "եղել", "ըլնի": "լինի", "ըլնել": "լինել",
    # other spoken forms
    "հմի": "հիմա", "հմա": "հիմա", "հեսա": "հիմա", "պտի": "պիտի", "ջահել": "երիտասարդ",
    "ձեն": "ձայն", "ձենս": "ձայնս", "ձենը": "ձայնը", "սաղ": "բոլոր", "հեչ": "բոլորովին", "խոսա": "խոսիր",
    "իսկականից": "իսկապես", "ախպեր": "եղբայր", "ախպերս": "եղբայրս", "ապեր": "եղբայր", "քուր": "քույր",
    "քուրս": "քույրս", "մամա": "մայրիկ", "պապա": "հայրիկ",
    # slang and Russian loans
    "ջոգում": "հասկանում", "ջոգել": "հասկանալ", "ջոգեցի": "հասկացա", "վաբշե": "ընդհանրապես",
    "վաբշ": "ընդհանրապես", "վապշե": "ընդհանրապես", "տիպա": "կարծես", "պրոստը": "պարզապես",
    "պրոստո": "պարզապես", "կոռոչե": "կարճ ասած", "կայֆ": "հաճույք",
}
# Fixed spoken phrases (as lower-case words without ՞ ՜ ՛) -> written form, and the form with ՞ when the phrase was
# asked: «Ի՞նչ կա չկա» -> «Ի՞նչ նորություն կա» (NLLB: "what's not there?").
SPOKEN_PHRASES = {
    ("ինչ", "կա", "չկա"): ("ինչ նորություն կա", "ի՞նչ նորություն կա"),
    ("մի", "հատ"): ("մի", "մի"),                  # filler «մի հատ ասա» = «մի ասա»; «երեք հատ» stays
    ("պետք", "չի"): ("պետք չէ", "պե՞տք չէ"),
}
# Spoken words asked as a question: the bare word (without ՞) -> written form with ՞ on its stressed vowel, wherever
# the ASR put the mark («ո՞նց», «ոնց՞»). Other words carrying ՞ ՜ ՛ are left as they are.
SPOKEN_QUESTIONS = {
    "ոնց": "ինչպե՞ս", "ինչի": "ինչո՞ւ", "ա": "է՞", "չի": "չէ՞",
    "կարում": "կարո՞ղ", "կարա": "կարո՞ղ", "կարաս": "կարո՞ղ ես", "կարամ": "կարո՞ղ եմ", "կարաք": "կարո՞ղ եք",
    "տենց": "այդպե՞ս", "սենց": "այսպե՞ս", "նենց": "այնպե՞ս", "էդպես": "այդպե՞ս", "էսպես": "այսպե՞ս",
    "էսօր": "այսօ՞ր", "էստեղ": "այստե՞ղ", "էդտեղ": "այդտե՞ղ", "էնտեղ": "այնտե՞ղ", "ստեղ": "այստե՞ղ",
}
_EDGE = re.compile(r"^(\W*)(.*?)(\W*)$")
_MARKS = "՞՜՛"


def _capital(new: str, old: str) -> str:
    return new[:1].upper() + new[1:] if new != old and old[:1].isupper() else new


def to_written(text: str) -> str:
    """Spoken -> written Armenian, for NLLB's input: «Էդ պահին նորմալ ա» -> «Այդ պահին նորմալ է».
    Fixed phrases first (SPOKEN_PHRASES), then word by word (SPOKEN_QUESTIONS for words with ՞, else
    SPOKEN_TO_WRITTEN). Punctuation and a capital first letter are kept. Also «չի» -> «չէ» at the end of a clause
    («լավ չի։»), where it means "is not"; elsewhere «չի» is written Armenian too («չի գալիս»)."""
    tokens = [_EDGE.match(t).groups() for t in text.split()]              # (lead, core, trail)
    bare = [re.sub(f"[{_MARKS}]", "", core).casefold() for _, core, _ in tokens]
    out, i = [], 0
    while i < len(tokens):
        for phrase, (plain, asked) in SPOKEN_PHRASES.items():
            n = len(phrase)
            if tuple(bare[i:i + n]) == phrase and not any(t[2].strip(_MARKS) for t in tokens[i:i + n - 1]):
                question = any("՞" in core + trail for _, core, trail in tokens[i:i + n])
                lead, trail = tokens[i][0], tokens[i + n - 1][2].replace("՞", "")
                out.append(lead + _capital(asked if question else plain, tokens[i][1]) + trail)
                i += n
                break
        else:
            lead, core, trail = tokens[i]
            if "՞" in core + trail:
                new = SPOKEN_QUESTIONS.get(bare[i], core)
                if new != core:
                    trail = trail.replace("՞", "")
            elif any(mark in core + trail for mark in _MARKS):      # «Ա՜» is an exclamation, not «է»
                new = core
            elif bare[i] in SPOKEN_TO_WRITTEN:
                new = SPOKEN_TO_WRITTEN[bare[i]]
            elif bare[i] == "չի" and (trail or i == len(tokens) - 1):
                new = "չէ"
            else:
                new = core
            out.append(lead + _capital(new, core) + trail)
            i += 1
    return " ".join(out)


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
    def __init__(self, model: str = "nllb-1.3b", beam_size: int = 1, threads: int = 4,
                 no_repeat_ngram_size: int = 4, repetition_penalty: float = 1.0,
                 spoken_to_written: bool = True) -> None:
        """Load the model once. If model files are missing, raise with a message saying how
        to download/convert them. No network after the first download.

        model: one of MODELS (default 1.3B since 2026-11-01, D3a; 600M is ~2x faster). beam_size: 1 = greedy (D3a: rated as good as beam 2 on our lines and
        23 % faster). threads: CPU threads for CTranslate2. no_repeat_ngram_size, repetition_penalty: against
        repetition loops (D3c, comment below). spoken_to_written: run to_written() on NLLB's input (D3d; on
        by default since 2026-11-01).
        """
        if model not in MODELS:
            raise ValueError(f"model must be one of {list(MODELS)}, got {model!r}")
        if beam_size < 1 or threads < 1:
            raise ValueError(f"beam_size and threads must be >= 1, got {beam_size}, {threads}")
        if no_repeat_ngram_size < 0 or repetition_penalty < 1.0:
            raise ValueError(f"no_repeat_ngram_size must be >= 0 and repetition_penalty >= 1.0, got "
                             f"{no_repeat_ngram_size}, {repetition_penalty}")
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
        # Against repetition loops («Սպասի, սպասի։» -> "Wait, wait, wait, ..." x15, live call 2026-11-01, chat 06):
        # no_repeat_ngram_size N forbids any N tokens from coming out twice (0 = off); repetition_penalty > 1 makes
        # tokens already written less likely (1.0 = off). CTranslate2 translate_batch options. D3c: 4 / 1.0 changed
        # the fewest other lines (6 of 71 real call lines, 1 of 29 test lines) and stopped the loop.
        self.no_repeat_ngram_size, self.repetition_penalty = no_repeat_ngram_size, repetition_penalty
        self.spoken_to_written = spoken_to_written        # D3d: to_written() on NLLB's input
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
        english = one_word_english(hy_text)
        if english is not None:
            return [Piece(hy_text.strip(), english, "glossary", None)]
        inputs = [to_written(p) for p in pieces] if self.spoken_to_written else pieces
        return [Piece(hy, en, "nllb", score, nllb_input=src if src != hy else None)
                for hy, src, (en, score) in zip(pieces, inputs, self.translate_pieces(inputs))]

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
            no_repeat_ngram_size=self.no_repeat_ngram_size, repetition_penalty=self.repetition_penalty,
            # an English sentence is about as long as its Armenian source; the cap stops a repetition loop
            max_decoding_length=min(256, 2 * max(len(s) for s in sources) + 10))
        out = []
        for result in results:
            tokens = result.hypotheses[0][1:]          # drop the target-language tag
            english = self._tokenizer.decode(self._tokenizer.convert_tokens_to_ids(tokens), skip_special_tokens=True)
            out.append((english.strip(), result.scores[0]))
        return out
