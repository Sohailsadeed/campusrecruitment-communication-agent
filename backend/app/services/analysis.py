"""Text analysis: speaking pace, filler words, clarity score."""
from __future__ import annotations

import re
from typing import Dict, List

FILLER_WORDS: List[str] = [
    "um",
    "uh",
    "like",
    "you know",
    "basically",
    "literally",
    "actually",
    "so",
    "well",
    "i mean",
    "right",
    "okay",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def count_words(text: str) -> int:
    """Count words, ignoring whitespace-only tokens."""
    tokens = re.findall(r"\b[\w']+\b", text)
    return len(tokens)


def detect_filler_words(text: str) -> Dict[str, int]:
    """Count occurrences of each filler word/phrase in text."""
    norm = _normalize(text)
    counts: Dict[str, int] = {}
    for filler in FILLER_WORDS:
        # Match as whole word(s) with word boundaries.
        pattern = r"\b" + re.escape(filler) + r"\b"
        found = len(re.findall(pattern, norm))
        if found > 0:
            counts[filler] = found
    return counts


def calculate_speaking_pace(text: str, duration_seconds: float) -> float:
    """Calculate words per minute."""
    if duration_seconds <= 0:
        return 0.0
    words = count_words(text)
    return round((words / duration_seconds) * 60.0, 2)


def calculate_clarity_score(
    total_words: int, filler_counts: Dict[str, int]
) -> float:
    """Clarity score on a 0-100 scale.

    Starts at 100 and subtracts 2 points per percentage point of filler usage.
    """
    if total_words <= 0:
        return 0.0
    total_fillers = sum(filler_counts.values())
    filler_pct = (total_fillers / total_words) * 100.0
    score = 100.0 - (filler_pct * 2.0)
    return round(max(0.0, min(100.0, score)), 2)


def analyze_transcription(text: str, duration_seconds: float) -> Dict[str, object]:
    """Perform full text analysis returning a metrics dict."""
    words = count_words(text)
    filler_counts = detect_filler_words(text)
    total_fillers = sum(filler_counts.values())
    pace = calculate_speaking_pace(text, duration_seconds)
    clarity = calculate_clarity_score(words, filler_counts)

    return {
        "word_count": words,
        "speaking_pace": pace,
        "filler_words_count": total_fillers,
        "filler_words_list": filler_counts,
        "clarity_score": clarity,
    }
