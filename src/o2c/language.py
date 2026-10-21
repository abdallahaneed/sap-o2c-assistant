"""Tiny language detector for German and English, based on common short words.

Good enough to tell the model which language to answer in, and to check answers
in the evaluation. No library needed.
"""

from __future__ import annotations

import re

DE_WORDS = {"der", "die", "das", "und", "ist", "nicht", "für", "mit", "den", "ein", "eine",
            "wurde", "sind", "auf", "dem", "es", "gibt", "noch", "zu", "im", "wo", "wie",
            "was", "wer", "welche", "bitte", "steht", "hoch", "warum"}  # fmt: skip
EN_WORDS = {"the", "and", "is", "are", "not", "of", "for", "with", "was", "were", "has",
            "this", "there", "to", "in", "it", "by", "be", "yet", "have", "what", "which",
            "who", "why", "how", "where", "please", "many", "does"}  # fmt: skip


def detect_language(text: str) -> str:
    """Return 'de' or 'en'. A tie goes to German, the main language of the app."""
    words = re.findall(r"[a-zäöüß]+", text.lower())
    de = sum(w in DE_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    return "en" if en > de else "de"
