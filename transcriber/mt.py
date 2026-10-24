"""MT module: Armenian text -> English text (NLLB-200 distilled, hye_Armn -> eng_Latn, D3).

Contract, tests and done-criteria: briefs/mt.md
"""


class Translator:
    def __init__(self) -> None:
        """Load the model once. If model files are missing, raise with a message saying how
        to download/convert them. No network after the first download."""
        raise NotImplementedError

    def translate(self, hy_text: str) -> str:
        """One segment of Armenian text (may hold several sentences) -> English text.

        Every sentence must appear in the output. "" -> "". Called from a single worker thread.
        """
        raise NotImplementedError
