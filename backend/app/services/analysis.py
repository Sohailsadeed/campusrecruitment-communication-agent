"""JAM (Just A Minute) Text & Speech Disfluency Analysis Engine.

Performs:
1. Context-aware filler word detection (excludes 'as well as', 'looks like', 'right now', etc.)
2. Repetition analysis (detects looping content words)
3. Acoustic pause analysis (silence duration, pause counts, longest pause)
4. Official JAM competition scoring rules & verdict
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Multi-word filler phrases
FILLER_PHRASES: List[str] = [
    "you know",
    "i mean",
    "kind of",
    "sort of",
    "you see",
    "like i said",
    "to be honest",
    "by the way",
    "at the end of the day",
]

# Stopwords to ignore during JAM repetition analysis
STOPWORDS = {
    "a", "an", "the", "and", "but", "or", "so", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all", "any",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
    "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she",
    "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
    "theirs", "themselves", "am", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "having", "do", "does", "did", "doing",
    "would", "should", "could", "ought", "i'm", "you're", "he's", "she's",
    "it's", "we're", "they're", "i've", "you've", "we've", "they've", "i'd",
    "you'd", "he'd", "she'd", "we'd", "they'd", "i'll", "you'll", "he'll",
    "she'll", "we'll", "they'll", "isn't", "aren't", "wasn't", "weren't",
    "hasn't", "haven't", "hadn't", "doesn't", "don't", "didn't", "won't",
    "wouldn't", "shan't", "shouldn't", "can't", "cannot", "couldn't", "mustn't",
    "let's", "that's", "who's", "what's", "here's", "there's", "when's",
    "where's", "why's", "how's", "not", "no", "yes", "can", "will", "may",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def count_words(text: str) -> int:
    """Count words, ignoring whitespace-only tokens."""
    tokens = re.findall(r"\b[\w']+\b", text)
    return len(tokens)


def detect_contextual_filler_words(text: str) -> Dict[str, int]:
    """Detect filler words with strict grammatical context awareness.
    
    Eliminates false positives like:
    - 'as well as' (conjunction) -> 'well' ignored
    - 'colour like having a car' (simile/comparison) -> 'like' ignored
    - 'right now' / 'right here' (adverb) -> 'right' ignored
    - 'so that' / 'so much' (degree/conjunction) -> 'so' ignored
    """
    if not text or not text.strip():
        return {}

    norm = _normalize(text)
    counts: Dict[str, int] = {}

    # 1. Phonetic Hesitations: ALWAYS fillers in speech
    phonetic_pattern = r"\b(um+|uh+|hmm+|er|ah)\b"
    for p in re.findall(phonetic_pattern, norm):
        counts[p] = counts.get(p, 0) + 1

    # 2. Multi-word phrases
    for phrase in FILLER_PHRASES:
        cnt = len(re.findall(r"\b" + re.escape(phrase) + r"\b", norm))
        if cnt > 0:
            counts[phrase] = cnt

    # 3. Contextual ambiguous words
    # 'well': exclude 'as well as', 'as well', 'well done', 'very well', 'well known'
    for m in re.finditer(r"\bwell\b", norm):
        idx = m.start()
        pre = norm[max(0, idx - 12):idx].strip()
        post = norm[idx + 4:min(len(norm), idx + 16)].strip()
        if (
            pre.endswith("as")
            or post.startswith("as")
            or pre.endswith("very")
            or pre.endswith("quite")
            or pre.endswith("get")
            or post.startswith("done")
            or post.startswith("known")
        ):
            continue  # Legitimate syntax
        counts["well"] = counts.get("well", 0) + 1

    # 'like': exclude comparisons and verbs
    for m in re.finditer(r"\blike\b", norm):
        idx = m.start()
        pre = norm[max(0, idx - 18):idx].strip()
        if re.search(
            r"\b(feel|feels|look|looks|sound|sounds|seem|seems|would|i|we|they|colour|color|something|things|such)\s*$",
            pre,
        ):
            continue  # Legitimate verb or comparison
        counts["like"] = counts.get("like", 0) + 1

    # 'right': exclude 'right now', 'right here', 'all right', 'that\'s right', 'right side'
    for m in re.finditer(r"\bright\b", norm):
        idx = m.start()
        pre = norm[max(0, idx - 12):idx].strip()
        post = norm[idx + 5:min(len(norm), idx + 16)].strip()
        if (
            pre.endswith("all")
            or pre.endswith("that's")
            or pre.endswith("you're")
            or post.startswith("now")
            or post.startswith("here")
            or post.startswith("side")
            or post.startswith("hand")
        ):
            continue
        counts["right"] = counts.get("right", 0) + 1

    # 'actually', 'basically', 'literally', 'obviously', 'seriously', 'totally'
    for word in ["actually", "basically", "literally", "obviously", "seriously", "totally"]:
        cnt = len(re.findall(r"\b" + re.escape(word) + r"\b", norm))
        if cnt > 0:
            counts[word] = cnt

    return counts


def detect_repetitions(text: str) -> Dict[str, int]:
    """Detect non-stopword words repeated 3+ times in a short JAM speech."""
    tokens = re.findall(r"\b[a-z]{3,}\b", text.lower())
    freq: Dict[str, int] = {}
    for tok in tokens:
        if tok in STOPWORDS:
            continue
        freq[tok] = freq.get(tok, 0) + 1

    repeated = {w: c for w, c in freq.items() if c >= 3}
    return dict(sorted(repeated.items(), key=lambda x: x[1], reverse=True))


def calculate_speaking_pace(text: str, duration_seconds: float) -> float:
    """Calculate words per minute."""
    if duration_seconds <= 0:
        return 0.0
    words = count_words(text)
    return round((words / duration_seconds) * 60.0, 2)


def evaluate_jam_rules(
    total_words: int,
    total_fillers: int,
    repetitions_count: int,
    duration_seconds: float,
    speaking_pace: float,
    total_pause_time: float,
    longest_pause: float,
) -> Tuple[float, str, List[str]]:
    """Compute official JAM score (0-100), verdict label, and infractions list."""
    infractions: List[str] = []
    penalty = 0.0

    # 1. Hesitation Penalty (Fillers + Acoustic Pauses)
    filler_penalty = min(35.0, total_fillers * 4.0)
    penalty += filler_penalty
    if total_fillers > 0:
        infractions.append(f"Hesitation: {total_fillers} filler sound(s) detected (-{filler_penalty:.0f} pts)")

    # Acoustic pause penalty (in 60s JAM, silence > 4s is an infraction)
    if total_pause_time > 4.0:
        pause_penalty = min(20.0, (total_pause_time - 3.0) * 2.5)
        penalty += pause_penalty
        infractions.append(f"Pauses: {total_pause_time:.1f}s of silence (longest pause: {longest_pause:.1f}s)")
    elif longest_pause >= 2.0:
        penalty += 8.0
        infractions.append(f"Long Pause: Hesitated in silence for {longest_pause:.1f}s")

    # 2. Repetition Penalty
    rep_penalty = min(25.0, repetitions_count * 5.0)
    penalty += rep_penalty
    if repetitions_count > 0:
        infractions.append(f"Repetition: {repetitions_count} repeated word loops (-{rep_penalty:.0f} pts)")

    # 3. Time Adherence (Target: 60s)
    if duration_seconds < 45:
        time_penalty = min(20.0, (45 - duration_seconds) * 0.8)
        penalty += time_penalty
        infractions.append(f"Time: Speech was short ({duration_seconds:.0f}s / 60s target)")
    elif duration_seconds > 68:
        time_penalty = min(15.0, (duration_seconds - 60) * 0.5)
        penalty += time_penalty
        infractions.append(f"Time: Overtime ({duration_seconds:.0f}s / 60s target)")

    # 4. Pace evaluation
    if speaking_pace > 0:
        if speaking_pace < 100:
            penalty += 5.0
            infractions.append("Pace: Speaking pace too slow (<100 WPM)")
        elif speaking_pace > 185:
            penalty += 5.0
            infractions.append("Pace: Speaking pace rushed (>185 WPM)")

    jam_score = round(max(0.0, min(100.0, 100.0 - penalty)), 1)

    # Official JAM Verdict
    if jam_score >= 85:
        verdict = "JAM Master 🏆 (Flawless Delivery)"
    elif jam_score >= 70:
        verdict = "Qualified ✅ (Solid JAM Round)"
    elif jam_score >= 50:
        verdict = "Challenged ⚠️ (Frequent Infractions)"
    else:
        verdict = "Disqualified ❌ (Multiple Rule Breaks)"

    return jam_score, verdict, infractions


def analyze_transcription(
    text: str,
    duration_seconds: float,
    pause_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Perform full context-aware JAM analysis with pause & disfluency metrics."""
    words = count_words(text)
    filler_counts = detect_contextual_filler_words(text)
    total_fillers = sum(filler_counts.values())
    repeated_words = detect_repetitions(text)
    pace = calculate_speaking_pace(text, duration_seconds)

    # Pause metrics
    p_data = pause_metrics or {}
    total_pause_time = float(p_data.get("total_pause_time", 0.0))
    longest_pause = float(p_data.get("longest_pause", 0.0))
    pause_count = int(p_data.get("pause_count", 0))

    jam_score, jam_verdict, infractions = evaluate_jam_rules(
        total_words=words,
        total_fillers=total_fillers,
        repetitions_count=len(repeated_words),
        duration_seconds=duration_seconds,
        speaking_pace=pace,
        total_pause_time=total_pause_time,
        longest_pause=longest_pause,
    )

    return {
        "word_count": words,
        "speaking_pace": pace,
        "filler_words_count": total_fillers,
        "filler_words_list": filler_counts,
        "clarity_score": jam_score,
        # Extended JAM metrics
        "jam_score": jam_score,
        "jam_verdict": jam_verdict,
        "hesitations_count": total_fillers,
        "repetitions_count": len(repeated_words),
        "repeated_words": repeated_words,
        "jam_infractions": infractions,
        "total_pause_time": total_pause_time,
        "pause_count": pause_count,
        "longest_pause": longest_pause,
    }
