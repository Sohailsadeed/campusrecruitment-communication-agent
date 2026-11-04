"""Deterministic speech analytics: what the candidate said, how they said it, and the evidence.

Everything here is computed from a transcript and the word-level timestamps an ASR engine produced
for it. Nothing is inferred from text alone about voice quality, emotion or confidence, and a metric
that the evidence cannot support is reported as unavailable rather than as zero — the two mean very
different things to a candidate reading their report.

The pause thresholds and the "silence is not speaking time" rule match ``app.services.transcription``
so that a JAM session and an HR answer are measured with one yardstick. Other interview modules can
call :func:`analyze_answer` directly; it takes plain data and returns plain data.
"""
from __future__ import annotations

import re
from statistics import pstdev
from typing import Any, Dict, List, Optional, Sequence

# Same boundaries app/services/transcription.py uses: 0.5s-1.19s is a micro-hesitation,
# >=1.2s is a real pause. Anything at or above UNUSUAL_PAUSE is worth telling the candidate about.
MICRO_PAUSE_SECONDS = 0.5
REAL_PAUSE_SECONDS = 1.2
UNUSUAL_PAUSE_SECONDS = 2.5

# A segment is long enough to measure a pace of its own only if it carries this many words.
MIN_WORDS_PER_SEGMENT = 4
# Rate figures are meaningless below this much actual speech.
MIN_SPEECH_SECONDS = 2.0

# Multi-word hedges are matched first so their words are not also counted singly.
FILLER_PHRASES = ("you know", "i mean", "at the end of the day", "sort of", "kind of",
                  "so to speak", "to be honest")
FILLER_WORDS = ("um", "uh", "erm", "ah", "hmm", "basically", "actually", "literally",
                "like", "yeah")
# "like" and "yeah" carry real meaning in ordinary sentences; these neighbouring words mark the
# comparative and the affirmative uses that must not be counted as hesitations.
LIKE_COMPARATIVE_BEFORE = ("feels", "felt", "looks", "look", "looked", "sounds", "sounded",
                           "seems", "seem", "seemed", "is", "was", "were", "as")
LIKE_NUMERIC_AFTER = re.compile(r"^\s*\d")
WORD = re.compile(r"[A-Za-z0-9']+")


def _words_of(text: str) -> List[str]:
    return WORD.findall(text or "")


def _spoken_word_count(text: str) -> int:
    """Count only real words. A hesitation token is not evidence of vocabulary, but it is speech.

    Hesitations are counted as spoken words here: they are time on the clock, and leaving them out
    would inflate the rate of someone who says "um" every few seconds.
    """
    return len(_words_of(text))


def analyze_answer(transcript: Optional[str],
                   words: Optional[Sequence[Dict[str, Any]]] = None,
                   segments: Optional[Sequence[Dict[str, Any]]] = None,
                   question: Optional[str] = None) -> Dict[str, Any]:
    """Measure one answer, and keep every number traceable to the transcript it came from.

    ``words`` and ``segments`` are the word-level timestamps ``transcribe_audio`` returns. Without
    them the timing metrics are unavailable; only what the text itself can prove is calculated.
    """
    text = (transcript or "").strip()
    timed = [w for w in (words or []) if _usable(w)]
    timed.sort(key=lambda w: float(w["start"]))
    unavailable: List[str] = []

    result: Dict[str, Any] = {
        "available": bool(text),
        "transcript_characters": len(text),
        "words_spoken": _spoken_word_count(text) if text else None,
        "speech_seconds": None,
        "silence_seconds": None,
        "words_per_minute": None,
        "pace_consistency": None,
        "pauses": None,
        "fillers": None,
        "conciseness": None,
        "observations": [],
        "unavailable": unavailable,
    }
    if not text:
        unavailable.extend(["words_per_minute", "silence_seconds", "pauses", "fillers",
                            "conciseness", "pace_consistency"])
        result["available"] = False
        return result

    if len(timed) >= 2:
        speech_seconds = round(sum(float(w["end"]) - float(w["start"]) for w in timed
                                   if float(w["end"]) > float(w["start"])), 2)
        span = round(float(timed[-1]["end"]) - float(timed[0]["start"]), 2)
        result["speech_seconds"] = speech_seconds
        result["silence_seconds"] = max(0.0, round(span - speech_seconds, 2))
        if speech_seconds >= MIN_SPEECH_SECONDS:
            # Rate over the time actually spoken: a candidate who stops for ten seconds is not a
            # slow talker, and a total-recording denominator would call them one.
            result["words_per_minute"] = round(
                result["words_spoken"] / (speech_seconds / 60.0), 1)
        else:
            unavailable.append("words_per_minute")
        result["pauses"] = _pauses(timed, text)
        result["pace_consistency"] = _pace_consistency(segments or _segments_from_words(timed))
        if result["pace_consistency"] is None:
            # One timed stretch proves nothing about how much the candidate's own rate varied.
            unavailable.append("pace_consistency")
    else:
        # No word-level timestamps: say so, and keep the text-only metrics.
        unavailable.extend(["words_per_minute", "silence_seconds", "pauses", "pace_consistency"])

    result["fillers"] = _fillers(text)
    result["conciseness"] = _conciseness(text, question, result["words_spoken"])

    result["observations"] = _observations(result, text)
    return result


# ---------------------------------------------------------------- components
def _usable(word: Dict[str, Any]) -> bool:
    try:
        start, end = float(word["start"]), float(word["end"])
    except (KeyError, TypeError, ValueError):
        return False
    return end >= start and bool(str(word.get("word", "")).strip())


def _pauses(timed: List[Dict[str, Any]], text: str) -> Dict[str, Any]:
    """Gaps between consecutive spoken words, split into ordinary and unusual.

    A gap is only evidence of silence when the two words around it are both real words; a timestamp
    that jumps because the engine mis-segmented a word is not something the candidate can fix, so the
    unusually long ones carry the words either side of them for verification.
    """
    real: List[Dict[str, Any]] = []
    micro: List[Dict[str, Any]] = []
    for current, following in zip(timed, timed[1:]):
        gap = round(float(following["start"]) - float(current["end"]), 2)
        if gap < MICRO_PAUSE_SECONDS:
            continue
        event = {
            "after_word": str(current.get("word", "")).strip(),
            "before_word": str(following.get("word", "")).strip(),
            "at_seconds": round(float(current["end"]), 2),
            "seconds": gap,
        }
        if gap >= REAL_PAUSE_SECONDS:
            real.append(event)
        else:
            micro.append(event)
    unusual = [p for p in real if p["seconds"] >= UNUSUAL_PAUSE_SECONDS]
    return {
        "count": len(real),
        "average_seconds": round(sum(p["seconds"] for p in real) / len(real), 2) if real else 0.0,
        "longest_seconds": max((p["seconds"] for p in real), default=0.0),
        "total_seconds": round(sum(p["seconds"] for p in real), 2),
        "ordinary_count": len(real) - len(unusual),
        "unusual": unusual,
        "micro_hesitation_count": len(micro),
        # Words the candidate left hanging: a pause with nothing after it is a timestamp artefact or
        # a cut-off recording, not a deliberate pause.
        "measured": bool(real or micro),
        "evidence": [p for p in (unusual or real)[:3] if _in_text(text, p["before_word"])],
    }


def _segments_from_words(timed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Synthesise one segment when only flat words are available, so continuity is still measurable."""
    if not timed:
        return []
    return [{"start": timed[0]["start"], "end": timed[-1]["end"],
             "words": timed, "text": " ".join(str(w.get("word", "")) for w in timed)}]


def _pace_consistency(segments: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """How much the candidate's own rate varied between their longest passages.

    Transcript-derived (word counts over timed spans) — it is about timing, not vocal quality, and it
    never calls a steady rate a "score".
    """
    rates: List[float] = []
    for segment in segments or []:
        seg_words = [w for w in (segment.get("words") or []) if _usable(w)]
        if len(seg_words) < MIN_WORDS_PER_SEGMENT:
            continue
        span = float(seg_words[-1]["end"]) - float(seg_words[0]["start"])
        if span >= MIN_SPEECH_SECONDS:
            rates.append(round(len(seg_words) / (span / 60.0), 1))
    if len(rates) < 2:
        return None
    spread = round(max(rates) - min(rates), 1)
    return {
        "segment_rates": rates,
        "spread_words_per_minute": spread,
        "variation_percent": round(pstdev(rates) / (sum(rates) / len(rates)) * 100, 1),
        "continuous_speech": spread <= 40.0,
    }


def _fillers(text: str) -> Dict[str, Any]:
    """Count hesitation words and phrases, refusing the ones used for their ordinary meaning.

    Ranges come from ``re.finditer`` over the transcript, so every quoted example is an exact
    substring of it by construction.
    """
    tokens = [(m.group(0), m.start(), m.end()) for m in WORD.finditer(text)]
    lowered = [t[0].lower() for t in tokens]
    hits: List[Dict[str, Any]] = []
    claimed: set = set()

    for phrase in FILLER_PHRASES:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            first = match.start()
            hits.append({"phrase": phrase, "excerpt": match.group(0),
                         "at_characters": [first, match.end()]})
            claimed.update(i for i, (_, s, e) in enumerate(tokens)
                           if s >= first and e <= match.end())

    for index, token in enumerate(lowered):
        if index in claimed or token not in FILLER_WORDS:
            continue
        if token == "like":
            before = lowered[index - 1] if index else ""
            after_raw = text[tokens[index][2]:tokens[index][2] + 2]
            if before in LIKE_COMPARATIVE_BEFORE or LIKE_NUMERIC_AFTER.match(after_raw):
                continue                      # "looks like", "like 30 percent": not a hesitation
        if token == "yeah":
            after = lowered[index + 1] if index + 1 < len(lowered) else ""
            if after in ("yeah", "uh", "um"):
                continue                      # a trailing affirmative already counted as a hedge
        hits.append({"phrase": token, "excerpt": tokens[index][0],
                     "at_characters": [tokens[index][1], tokens[index][2]]})

    spoken = _spoken_word_count(text)
    by_phrase: Dict[str, int] = {}
    for hit in hits:
        by_phrase[hit["phrase"]] = by_phrase.get(hit["phrase"], 0) + 1
    return {
        "count": len(hits),
        "per_100_words": round(len(hits) / spoken * 100, 1) if spoken else None,
        "by_phrase": by_phrase,
        "examples": [h["excerpt"] for h in hits[:6]],
        "measured_from": "transcript",
    }


def _conciseness(text: str, question: Optional[str],
                 words_spoken: Optional[int]) -> Dict[str, Any]:
    """Repetition, preamble and whether the answer ever landed — never length alone.

    A ninety-word STAR answer that says each thing once is not rambling, so no signal below is
    derived from word count on its own.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    repeated = _repeated_phrases(text)

    preamble = None
    opener = ""
    for match in re.finditer(r"\bI\s+(?:\w+ed\b|was\b|took\b|made\b|built\b|owned\b|"
                             r"decided\b|led\b|shipped\b|fixed\b|wrote\b|reduced\b)",
                             text, re.IGNORECASE):
        preamble = len(_words_of(text[:match.start()]))
        opener = text[:max(match.end(), 40)]
        break

    closing = sentences[-1] if sentences else ""
    trailing = bool(re.search(r"\b(and\s+yeah|so yeah|um|uh|you know)\b[^.!?]*$",
                              closing, re.IGNORECASE))
    conclusion_reached = bool(closing) and len(_words_of(closing)) >= 4 and not trailing

    signals: List[str] = []
    if repeated:
        signals.append("repeated_point")
    if preamble is not None and preamble > 25:
        signals.append("long_introduction")
    if not conclusion_reached:
        signals.append("no_clear_conclusion")
    ratio = None
    if question and words_spoken:
        asked = _spoken_word_count(question)
        if asked:
            ratio = round(words_spoken / asked, 1)
            if ratio > 12.0 and signals:
                signals.append("long_relative_to_question")

    return {
        "words": words_spoken,
        "sentences": len(sentences),
        "repeated_phrases": repeated,
        "preamble_words_before_first_personal_action": preamble,
        "introduction_excerpt": _excerpt(opener) if preamble is not None and preamble > 25 else None,
        "closing_excerpt": _excerpt(closing) if closing else None,
        "conclusion_reached": conclusion_reached,
        "words_per_question_word": ratio,
        "rambling_signals": signals,
        "rambling": bool(repeated) or (preamble is not None and preamble > 25)
        or not conclusion_reached,
    }


def _repeated_phrases(text: str) -> List[Dict[str, Any]]:
    """Repeated four- or five-word runs, quoted from the transcript at their original offsets.

    The longer run is matched first, so a restatement is reported once — as the longest stretch of
    words that came back — rather than as three overlapping fragments of the same sentence.
    """
    tokens = [(m.group(0), m.start(), m.end()) for m in WORD.finditer(text)]
    lowered = [t[0].lower() for t in tokens]
    stop = {"the", "a", "an", "and", "of", "to", "in", "i", "we", "my", "our", "was", "were",
            "is", "are", "that", "it", "for", "with", "on"}
    runs: Dict[str, Dict[str, Any]] = {}
    for size in (5, 4):
        for i in range(len(lowered) - size + 1):
            gram = lowered[i:i + size]
            if sum(1 for g in gram if g in stop) > size // 2:
                continue
            phrase = " ".join(gram)
            if any(phrase != known and phrase in known for known in runs):
                continue                          # already covered by a longer run
            runs.setdefault(phrase, {"size": size, "positions": []})["positions"].append(i)
    repeated = []
    for phrase, run in runs.items():
        positions = run["positions"]
        if len(positions) < 2:
            continue
        first = positions[0]
        excerpt = text[tokens[first][1]:tokens[first + run["size"] - 1][2]].strip()
        repeated.append({"phrase": phrase, "occurrences": len(positions),
                         "excerpt": _excerpt(excerpt)})
    repeated.sort(key=lambda r: (-r["occurrences"], -len(r["phrase"])))
    return repeated[:3]


# ---------------------------------------------------------------- evidence
def _observations(result: Dict[str, Any], text: str) -> List[Dict[str, str]]:
    """Plain sentences, each carrying a quote that exists in the transcript.

    The check at the end is not decoration: an observation whose excerpt cannot be found in the
    original words is dropped rather than shown.
    """
    out: List[Dict[str, str]] = []
    words = result.get("words_spoken") or 0
    fillers = result.get("fillers") or {}
    if fillers.get("count"):
        out.append({"metric": "fillers",
                    "text": f"You used {fillers['count']} filler word"
                            f"{'s' if fillers['count'] != 1 else ''} in a {words}-word answer "
                            f"({fillers.get('per_100_words')} per 100 words).",
                    "excerpt": ", ".join(f'"{e}"' for e in fillers.get("examples", [])[:3])})
    pauses = result.get("pauses") or {}
    for unusual in (pauses.get("unusual") or [])[:2]:
        if not (_in_text(text, unusual["before_word"])
                and _in_text(text, unusual["after_word"])):
            continue
        out.append({"metric": "pauses",
                    "text": f"You paused for about {unusual['seconds']} seconds after "
                            f'"{unusual["after_word"]}", just before "{unusual["before_word"]}".',
                    "excerpt": unusual["before_word"]})
    pace = result.get("words_per_minute")
    if pace:
        out.append({"metric": "words_per_minute",
                    "text": f"You spoke {pace} words per minute over {result['speech_seconds']} "
                            f"seconds of actual speech (silence excluded).",
                    "excerpt": ""})
    concise = result.get("conciseness") or {}
    for phrase in (concise.get("repeated_phrases") or [])[:2]:
        if _in_text(text, phrase["excerpt"]):
            out.append({"metric": "repetition",
                        "text": f'You made the same point twice: "{phrase["excerpt"]}" appears '
                                f'{phrase["occurrences"]} times.',
                        "excerpt": phrase["excerpt"]})
    if concise.get("introduction_excerpt") and _in_text(text, concise["introduction_excerpt"]):
        out.append({"metric": "preamble",
                    "text": f"You used {concise['preamble_words_before_first_personal_action']} "
                            f"words before saying what you yourself did.",
                    "excerpt": concise["introduction_excerpt"]})
    if concise.get("closing_excerpt") and not concise.get("conclusion_reached") \
            and _in_text(text, concise["closing_excerpt"]):
        out.append({"metric": "conclusion",
                    "text": "Your answer trailed off instead of landing on a result.",
                    "excerpt": concise["closing_excerpt"]})
    return [o for o in out if not o["excerpt"] or _in_text(text, o["excerpt"])]


def _in_text(text: str, excerpt: Optional[str]) -> bool:
    return bool(excerpt) and excerpt in text


def _excerpt(value: str, limit: int = 70) -> str:
    """Shorten a quotation without breaking it away from the transcript.

    An ellipsis makes the text unmatchable against the source, and an observation the report cannot
    point back to is worth less than no observation, so excerpts are cut at a word or comma boundary
    and stay exact substrings.
    """
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    head = value[:limit]
    cut = max(head.rfind(" "), head.rfind(","))
    return (head[:cut] if cut > 20 else head).strip()


# ---------------------------------------------------------------- trends
def session_metrics(questions: Optional[Sequence[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Average the per-answer speech figures of one completed round, ignoring unavailable ones."""
    collected: Dict[str, List[float]] = {}
    for question in questions or []:
        speech = question.get("speech")
        if not isinstance(speech, dict) or not speech.get("available"):
            continue
        for key in ("words_per_minute", "silence_seconds"):
            value = speech.get(key)
            if isinstance(value, (int, float)):
                collected.setdefault(key, []).append(float(value))
        fillers = speech.get("fillers") or {}
        if isinstance(fillers.get("per_100_words"), (int, float)):
            collected.setdefault("fillers_per_100_words", []).append(
                float(fillers["per_100_words"]))
        pauses = speech.get("pauses") or {}
        if isinstance(pauses.get("average_seconds"), (int, float)) and pauses.get("count"):
            collected.setdefault("pause_seconds", []).append(float(pauses["average_seconds"]))
        concise = speech.get("conciseness") or {}
        if isinstance(concise.get("words"), (int, float)):
            collected.setdefault("answer_words", []).append(float(concise["words"]))
    if not collected:
        return None
    return {key: round(sum(values) / len(values), 2) for key, values in collected.items()}


def round_report_block(questions: Optional[Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
    """What a finished round sounded like, answer by answer, with every claim tied to its transcript.

    Answers written before this module existed carry no ``speech`` entry; they appear in
    ``missing_speech`` rather than being averaged in as zeros.
    """
    answers: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    missing: List[int] = []
    for number, question in enumerate(questions or [], start=1):
        speech = question.get("speech")
        if not isinstance(speech, dict) or not speech:
            # An answer written by the voice lane before this module existed carries an empty dict.
            # That is no data, not a round in which nothing was measured.
            missing.append(number)
            continue
        pauses = speech.get("pauses") or {}
        concise = speech.get("conciseness") or {}
        answers.append({
            "question_number": number,
            "question": _excerpt(str(question.get("text", "")), 90),
            "available": bool(speech.get("available")),
            "words_spoken": speech.get("words_spoken"),
            "words_per_minute": speech.get("words_per_minute"),
            "speech_seconds": speech.get("speech_seconds"),
            "silence_seconds": speech.get("silence_seconds"),
            "pace_consistency": speech.get("pace_consistency"),
            "filler_count": (speech.get("fillers") or {}).get("count"),
            "fillers_per_100_words": (speech.get("fillers") or {}).get("per_100_words"),
            "pause_count": pauses.get("count"),
            "longest_pause_seconds": pauses.get("longest_seconds"),
            "unusual_pause_count": len(pauses.get("unusual") or []),
            "rambling_signals": concise.get("rambling_signals"),
            "repeated_phrases": concise.get("repeated_phrases"),
            "unavailable": speech.get("unavailable") or [],
        })
        for observation in speech.get("observations") or []:
            observations.append({"question_number": number, **observation})
    return {"averages": session_metrics(questions), "answers": answers,
            "observations": observations, "answers_without_speech_data": missing}


def trends(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compare comparable metrics across completed rounds, oldest first.

    A metric only appears when it was measured in both of the rounds being compared — a missing
    figure never becomes a zero, and never becomes an improvement.
    """
    measured = [r for r in rows if isinstance(r.get("metrics"), dict)]
    if len(measured) < 2:
        return None
    previous, latest = measured[-2], measured[-1]
    shared = sorted(set(previous["metrics"]) & set(latest["metrics"]))
    if not shared:
        return None
    return {
        "from_session_id": previous.get("session_id"),
        "to_session_id": latest.get("session_id"),
        "rounds_compared": len(measured),
        "changes": {
            key: {
                "previous": previous["metrics"][key],
                "latest": latest["metrics"][key],
                "delta": round(latest["metrics"][key] - previous["metrics"][key], 2),
            } for key in shared
        },
        "not_compared": sorted({k for r in measured for k in r["metrics"]} - set(shared)),
    }
