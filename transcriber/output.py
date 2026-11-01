"""Terminal output: one entry per phrase, as in the brief (time, speaker, Armenian, English). briefs/integration.md

    [00:01:12] Speaker 1
      HY: Բարև, ինչպե՞ս ես։
      EN: Hi, how are you?
"""


def clock(seconds: float) -> str:
    """Session seconds -> hh:mm:ss."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_entry(start: float, speaker: str, hy_text: str, en_text: str) -> str:
    """One entry; it ends with a newline, so print() leaves a blank line between entries."""
    return f"[{clock(start)}] {speaker}\n  HY: {hy_text}\n  EN: {en_text}\n"
