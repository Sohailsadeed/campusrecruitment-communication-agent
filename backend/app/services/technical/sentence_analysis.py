"""Deterministic sentence segmentation and checkpoint tagging for Technical answers."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_SENTENCE_END_RE = re.compile(r"[.!?]+[\"')\]]*$")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip())


def _word_count(text: str) -> int:
    return len(text.split())


def _chunk_words(text: str, max_words: int) -> List[str]:
    words = text.split()
    return [
        " ".join(words[idx : idx + max_words])
        for idx in range(0, len(words), max_words)
    ]


def _merge_clauses(clauses: List[str], max_words: int) -> List[str]:
    """Merge short clauses up to a readable length without crossing a clause too far."""
    merged: List[str] = []
    current: List[str] = []
    current_words = 0

    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        clause_words = _word_count(clause)
        if clause_words > max_words:
            if current:
                merged.append(" ".join(current))
                current = []
                current_words = 0
            merged.extend(_chunk_words(clause, max_words))
            continue
        if current and current_words + clause_words > max_words:
            merged.append(" ".join(current))
            current = []
            current_words = 0
        current.append(clause)
        current_words += clause_words

    if current:
        merged.append(" ".join(current))
    return merged


def build_sentences_from_text(text: str, max_words: int = 42) -> List[Dict[str, Any]]:
    """Split plain answer text into sentence units without inventing timestamps."""
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", cleaned) if p.strip()]
    if len(parts) == 1 and _word_count(parts[0]) > max_words:
        # Browser speech transcripts often lack terminal punctuation. Treat
        # clause boundaries as the best available sentence proxy.
        parts = [p.strip() for p in re.split(r"(?<=[,;:])\s+", parts[0]) if p.strip()]

    sentences: List[str] = []
    for part in parts:
        if _word_count(part) > max_words:
            clauses = [p.strip() for p in re.split(r"(?<=[,;:])\s+", part) if p.strip()]
            sentences.extend(_merge_clauses(clauses, max_words) if clauses else [part])
        else:
            sentences.append(part)

    return [
        {
            "index": idx,
            "text": text_part,
            "start": None,
            "end": None,
            "is_conclusion_checkpoint": False,
            "is_rambling": False,
            "highlight": "none",
        }
        for idx, text_part in enumerate(sentences)
        if text_part
    ]


def build_sentences_from_words(
    words: List[Dict[str, Any]],
    max_words: int = 42,
    pause_boundary: float = 0.9,
) -> List[Dict[str, Any]]:
    """Build sentence spans from ASR word timestamps.

    Sentence boundaries come from terminal punctuation, a substantial silence
    gap, or a maximum length guard. This gives the report real start/end times
    for click-to-replay diagnostics.
    """
    if not words:
        return []

    sentences: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        raw_text = " ".join(str(w.get("word", "")).strip() for w in current)
        raw_text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", raw_text).strip()
        if raw_text:
            sentences.append(
                {
                    "index": len(sentences),
                    "text": raw_text,
                    "start": round(float(current[0].get("start", 0.0)), 2),
                    "end": round(float(current[-1].get("end", 0.0)), 2),
                    "is_conclusion_checkpoint": False,
                    "is_rambling": False,
                    "highlight": "none",
                }
            )
        current = []

    for idx, word in enumerate(words):
        token = str(word.get("word", "")).strip()
        if not token:
            continue
        current.append(word)

        next_gap = 0.0
        if idx + 1 < len(words):
            next_gap = float(words[idx + 1].get("start", 0.0)) - float(
                word.get("end", 0.0)
            )

        if (
            _SENTENCE_END_RE.search(token)
            or next_gap >= pause_boundary
            or len(current) >= max_words
        ):
            flush()

    flush()
    return sentences


def format_sentences_for_prompt(sentences: List[Dict[str, Any]]) -> str:
    """Render numbered sentences for the evaluator prompt."""
    if not sentences:
        return "(No sentence segmentation available.)"
    return "\n".join(
        f"[{int(item.get('index', idx))}] {str(item.get('text', '')).strip()}"
        for idx, item in enumerate(sentences)
    )


def _coerce_index(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_indices(value: Any) -> List[int]:
    """Accept list/string outputs from LLMs and return unique integer indices."""
    if value is None:
        return []
    if isinstance(value, str):
        raw_values: List[Any] = re.findall(r"\d+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]

    indices: List[int] = []
    for raw in raw_values:
        idx = _coerce_index(raw)
        if idx is not None and idx >= 0 and idx not in indices:
            indices.append(idx)
    return indices


def apply_sentence_labels(
    sentences: List[Dict[str, Any]],
    checkpoint_index: Any,
    rambling_indices: Any,
    rambling_critique: str = "",
) -> tuple[List[Dict[str, Any]], Optional[int]]:
    """Validate LLM indices and attach checkpoint/rambling UI flags."""
    tagged: List[Dict[str, Any]] = [dict(item) for item in sentences]
    if not tagged:
        return [], None

    checkpoint = _coerce_index(checkpoint_index)
    if checkpoint is not None and not (0 <= checkpoint < len(tagged)):
        checkpoint = None

    rambling = {
        idx
        for idx in coerce_indices(rambling_indices)
        if 0 <= idx < len(tagged) and idx != checkpoint
    }
    if checkpoint is not None:
        rambling = {idx for idx in rambling if idx > checkpoint}

    critique = (rambling_critique or "").strip()
    for idx, sentence in enumerate(tagged):
        is_checkpoint = idx == checkpoint
        is_rambling = idx in rambling
        sentence["index"] = idx
        sentence["is_conclusion_checkpoint"] = is_checkpoint
        sentence["is_rambling"] = is_rambling
        if is_rambling:
            sentence["highlight"] = "red"
            sentence["rationale"] = critique or (
                "Circular or padded statement after the core answer was complete."
            )
        elif is_checkpoint:
            sentence["highlight"] = "green"
            sentence["rationale"] = "Core answer is complete at this sentence."
        else:
            sentence["highlight"] = "none"
            sentence.pop("rationale", None)

    return tagged, checkpoint
