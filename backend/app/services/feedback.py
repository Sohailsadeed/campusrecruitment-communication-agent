"""JAM (Just A Minute) LLM-backed feedback evaluation via Ollama."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests

from config import settings

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are an expert Chief Adjudicator & Executive Communication Coach for high-stakes interviews and speaking rounds.
The speaker chose this specific topic/drill: "{topic}"

Speech & Acoustic Analytics:
- Selected Topic: "{topic}"
- Speaking pace: {speaking_pace} WPM
- Total Silence/Pause Time: {total_pause_time}s across {pause_count} pauses (longest pause: {longest_pause}s)
- Hesitations / Filler sounds count: {filler_count} ({filler_list})
- Repeated content words: {repetition_count} ({repetition_list})
- Calculated Score: {jam_score}/100 | Verdict: {jam_verdict}

Transcript:
"{transcript}"

As the Chief Coach:
1. Deliver a concise 3-5 sentence adjudication addressing topic delivery, clarity, structure, and flow.
2. Select 1 or 2 specific weak phrases/sentences from the transcript (especially where filler words, vagueness, or repetition occurred) and provide executive-level "Critical Moment Rewrites" side-by-side with original vs polished version, letter grades, and actionable tips.
3. Score the 6 Core Competency Vectors (0-100 each):
   - Articulation & Acoustic Clarity
   - Structure & STAR Logic Flow
   - Technical Depth & Precision
   - Pacing & Strategic Pauses
   - Confidence & Assertive Tone
   - Conciseness (Low Fluff)
4. Highlight 2-3 observed mastery points and 2 curated follow-up drills.

Respond ONLY with a JSON object with these exact keys:
{{
  "content": "<paragraph of judge adjudication addressing topic adherence, hesitations, and delivery>",
  "score": {jam_score},
  "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"],
  "rewrites": [
    {{
      "timestamp": "00:15",
      "original": "<exact weak sentence or colloquial phrase from transcript>",
      "polish": "<quantified, concise, high-impact executive rewrite of that sentence>",
      "grade": "C+",
      "polish_grade": "A+",
      "tip": "<specific rationale for the improvement>"
    }}
  ],
  "competencies": {{
    "articulation": 88,
    "structure": 85,
    "technical_depth": 84,
    "pacing": 82,
    "confidence": 86,
    "conciseness": 80
  }},
  "mastery_points": [
    {{"title": "Decisive Framing", "description": "Addressed key problem constraints directly without defensive language."}},
    {{"title": "Executive Voice", "description": "Used direct active voice rather than passive qualifiers."}}
  ],
  "curated_drills": [
    {{"title": "Conciseness Squeezer Drill", "desc": "Condense 2-min answers into 45s", "duration": "8 mins", "icon": "timer"}},
    {{"title": "Filler Word Elimination", "desc": "Real-time haptic/visual cueing", "duration": "7 mins", "icon": "bolt"}}
  ]
}}
"""


def _build_prompt(metrics: Dict[str, Any], transcript: str, topic: str = "General Topic") -> str:
    fillers = metrics.get("filler_words_list") or {}
    clean_fillers = {k: v for k, v in fillers.items() if k != "_jam"}
    filler_list = ", ".join(f"{k} x{v}" for k, v in clean_fillers.items()) or "none"

    reps = metrics.get("repeated_words") or {}
    rep_list = ", ".join(f"'{k}' x{v}" for k, v in reps.items()) or "none"

    excerpt = (transcript or "").strip()
    if len(excerpt) > 800:
        excerpt = excerpt[:800] + "..."

    return PROMPT_TEMPLATE.format(
        topic=topic or "Impromptu Speech",
        speaking_pace=metrics.get("speaking_pace", 0),
        total_pause_time=metrics.get("total_pause_time", 0.0),
        pause_count=metrics.get("pause_count", 0),
        longest_pause=metrics.get("longest_pause", 0.0),
        filler_count=metrics.get("filler_words_count", 0),
        filler_list=filler_list,
        repetition_count=metrics.get("repetitions_count", 0),
        repetition_list=rep_list,
        jam_score=metrics.get("jam_score", metrics.get("clarity_score", 70)),
        jam_verdict=metrics.get("jam_verdict", "Qualified"),
        transcript=excerpt,
    )


def _heuristic_feedback(metrics: Dict[str, Any], topic: str = "Impromptu Speech", transcript: str = "") -> Dict[str, Any]:
    """Deterministic fallback feedback with VerbalIQ rewrites and competency vector."""
    pace = float(metrics.get("speaking_pace") or 0)
    fillers = int(metrics.get("filler_words_count") or 0)
    reps = int(metrics.get("repetitions_count") or 0)
    pauses = float(metrics.get("total_pause_time") or 0.0)
    longest_pause = float(metrics.get("longest_pause") or 0.0)
    score = float(metrics.get("jam_score", metrics.get("clarity_score", 78.0)) or 78.0)
    verdict = str(metrics.get("jam_verdict") or "Qualified")

    parts: List[str] = [f"Adjudication for topic '{topic}': Verdict is {verdict} ({score:.0f}/100)."]
    suggestions: List[str] = []

    # Calculate 6-axis competencies
    base_art = min(96, max(65, int(score + 4)))
    base_struct = min(94, max(60, int(score + (2 if reps == 0 else -6))))
    base_tech = min(92, max(65, int(score + 3)))
    base_pace = min(95, max(58, int(92 - abs(pace - 145) * 0.6)))
    base_conf = min(95, max(62, int(score - (3 if longest_pause > 2.0 else 0))))
    base_concise = min(94, max(50, int(90 - fillers * 5 - reps * 4)))

    competencies = {
        "articulation": base_art,
        "structure": base_struct,
        "technical_depth": base_tech,
        "pacing": base_pace,
        "confidence": base_conf,
        "conciseness": base_concise,
    }

    if fillers == 0 and pauses < 3.0:
        parts.append("Outstanding fluency with zero hesitation infractions and clean pacing.")
    elif fillers <= 2:
        parts.append(f"Minor hesitation with {fillers} filler sound(s) and {pauses:.1f}s total pause time.")
        suggestions.append("Breathe and convert micro-hesitations into intentional theatrical pauses.")
    else:
        parts.append(f"Challenged on hesitation: {fillers} filler sounds detected and {pauses:.1f}s of silence.")
        suggestions.append("Drill the 'silence drill': pause deliberately rather than defaulting to audible fillers.")

    if reps == 0:
        parts.append("Great vocabulary variety with no repetitive content loops.")
    else:
        parts.append(f"Flagged for repetition: repeated {reps} content words excessively.")
        suggestions.append("Branch your topic into distinct pillars (Context, Action, Outcome) to avoid circular phrasing.")

    if longest_pause >= 2.0:
        parts.append(f"Experienced a noticeable freeze of {longest_pause:.1f}s.")
        suggestions.append("Use a transitional bridge ('Furthermore...', 'On the other hand...') rather than dead silence.")

    if len(suggestions) < 3:
        suggestions.append(f"Keep practicing impromptu delivery on topics like '{topic}' using structured synthesis.")

    # Generate realistic Critical Moment Rewrites
    rewrites = []
    text_clean = (transcript or "").strip()
    sentences = [s.strip() for s in text_clean.split(".") if len(s.strip().split()) >= 4]

    filler_sentence = next((s for s in sentences if any(f in s.lower() for f in ["basically", "like", "you know", "um", "uh"])), None)
    if filler_sentence:
        cleaned_sub = filler_sentence
        for f in ["basically", "you know", "like", "um", "uh"]:
            cleaned_sub = cleaned_sub.replace(f, "").replace(f.capitalize(), "")
        cleaned_sub = " ".join(cleaned_sub.split())
        rewrites.append({
            "timestamp": "00:14",
            "original": f'"{filler_sentence}."',
            "polish": f'"To achieve maximum impact, {cleaned_sub.lower()} with targeted execution."',
            "grade": "C+",
            "polish_grade": "A+",
            "tip": "Substitute colloquial qualifiers with direct, quantified ownership statements."
        })
    else:
        sample_s = sentences[0] if sentences else f"Explaining {topic} effectively."
        rewrites.append({
            "timestamp": "00:18",
            "original": f'"{sample_s}."',
            "polish": f'"Specifically regarding {topic}, we deployed structured milestones to increase throughput by 35%."',
            "grade": "B",
            "polish_grade": "A+",
            "tip": "Ground technical statements with concrete metrics and architectural specifics."
        })

    mastery_points = [
        {"title": "Decisive Tradeoff Framing", "description": f"Directly framed key considerations when addressing '{topic}'."},
        {"title": "Executive Ownership Voice", "description": "Maintained active leadership cadence with clear vocal presence."},
        {"title": "Active Breath Management", "description": f"Preserved steady acoustic flow ({int(pace)} WPM) under speaking pressure."}
    ]

    curated_drills = [
        {"title": "Conciseness Squeezer Drill", "desc": "Condense 2-min answers into 45s", "duration": "8 mins", "icon": "timer"},
        {"title": "Filler Word Elimination", "desc": "Real-time haptic/visual cueing", "duration": "7 mins", "icon": "bolt"}
    ]

    return {
        "content": " ".join(parts),
        "score": score,
        "suggestions": suggestions[:3],
        "rewrites": rewrites,
        "competencies": competencies,
        "mastery_points": mastery_points,
        "curated_drills": curated_drills,
    }


def generate_feedback(
    metrics: Dict[str, Any],
    transcript: str,
    topic: str = "Impromptu Speech",
) -> Dict[str, Any]:
    """Generate comprehensive VerbalIQ feedback with rewrites, competencies, and drills."""
    prompt = _build_prompt(metrics, transcript, topic)
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"

    try:
        response = requests.post(
            url,
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3},
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        raw = data.get("response", "").strip()
        if not raw:
            raise ValueError("Empty Ollama response")
        parsed = json.loads(raw)
        
        fallback = _heuristic_feedback(metrics, topic, transcript)
        return {
            "content": str(parsed.get("content", "")).strip() or fallback["content"],
            "score": float(parsed.get("score", metrics.get("jam_score", 0)) or fallback["score"]),
            "suggestions": [str(s) for s in parsed.get("suggestions", [])][:5] or fallback["suggestions"],
            "rewrites": parsed.get("rewrites") or fallback["rewrites"],
            "competencies": parsed.get("competencies") or fallback["competencies"],
            "mastery_points": parsed.get("mastery_points") or fallback["mastery_points"],
            "curated_drills": parsed.get("curated_drills") or fallback["curated_drills"],
        }
    except Exception as exc:
        logger.info("Ollama unavailable, using enhanced heuristic feedback: %s", exc)
        return _heuristic_feedback(metrics, topic, transcript)

