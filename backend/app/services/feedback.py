"""LLM-backed feedback generation via Ollama."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import requests

from config import settings

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are SpeakFlow, an expert public speaking coach.
Given the following analytics from a practice session, write concise, encouraging
feedback (4-6 sentences) and 3 concrete, actionable suggestions.

Metrics:
- Speaking pace: {speaking_pace} words per minute (ideal 130-160)
- Filler words used: {filler_count} ({filler_list})
- Clarity score: {clarity_score}/100
- Eye contact: {eye_contact}%
- Posture quality: {posture}/100

Transcript excerpt:
"{transcript}"

Respond ONLY with a JSON object with these exact keys:
{{
  "content": "<paragraph of feedback>",
  "score": <overall 0-100 number>,
  "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"]
}}
"""


def _build_prompt(metrics: Dict[str, Any], transcript: str) -> str:
    fillers = metrics.get("filler_words_list") or {}
    filler_list = ", ".join(f"{k} x{v}" for k, v in fillers.items()) or "none"
    excerpt = (transcript or "").strip()
    if len(excerpt) > 500:
        excerpt = excerpt[:500] + "..."
    return PROMPT_TEMPLATE.format(
        speaking_pace=metrics.get("speaking_pace", 0),
        filler_count=metrics.get("filler_words_count", 0),
        filler_list=filler_list,
        clarity_score=metrics.get("clarity_score", 0),
        eye_contact=metrics.get("eye_contact_percentage", 0),
        posture=metrics.get("posture_quality", 0),
        transcript=excerpt,
    )


def _heuristic_feedback(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback feedback when Ollama is unreachable."""
    pace = float(metrics.get("speaking_pace") or 0)
    fillers = int(metrics.get("filler_words_count") or 0)
    clarity = float(metrics.get("clarity_score") or 0)
    eye = float(metrics.get("eye_contact_percentage") or 0)
    posture = float(metrics.get("posture_quality") or 0)

    parts: List[str] = []
    suggestions: List[str] = []

    if pace == 0:
        parts.append("Record a longer sample so we can measure your pace accurately.")
    elif pace < 120:
        parts.append("Your speaking pace is slower than the 130-160 WPM sweet spot.")
        suggestions.append("Practice reading aloud at a slightly brisker pace to energize the delivery.")
    elif pace > 170:
        parts.append("You're speaking faster than the ideal range, which can make it hard for listeners to follow.")
        suggestions.append("Insert deliberate pauses between key ideas to let your points land.")
    else:
        parts.append("Your pace is right in the ideal zone - natural and easy to follow.")

    if fillers > 0:
        parts.append(f"You used {fillers} filler words, which dilutes your message.")
        suggestions.append("Replace filler words with brief pauses - silence reads as confident.")
    else:
        parts.append("Impressively, you used no filler words in this session.")

    parts.append(f"Your clarity score is {clarity:.0f}/100 and your on-camera presence (eye contact {eye:.0f}%, posture {posture:.0f}) is solid.")
    if eye < 70:
        suggestions.append("Aim your gaze closer to the lens to strengthen the sense of eye contact.")
    if posture < 75:
        suggestions.append("Roll your shoulders back and ground both feet to project more confidence.")
    if len(suggestions) < 3:
        suggestions.append("Record a 60 second follow-up focused on one improvement area at a time.")

    overall = round((clarity * 0.5) + (eye * 0.25) + (posture * 0.25), 2)
    return {
        "content": " ".join(parts),
        "score": overall,
        "suggestions": suggestions[:3],
    }


def generate_feedback(
    metrics: Dict[str, Any],
    transcript: str,
) -> Dict[str, Any]:
    """Generate coaching feedback, preferring Ollama, falling back to heuristics."""
    prompt = _build_prompt(metrics, transcript)
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"

    try:
        response = requests.post(
            url,
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.4},
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        raw = data.get("response", "").strip()
        if not raw:
            raise ValueError("Empty Ollama response")
        parsed = json.loads(raw)
        return {
            "content": str(parsed.get("content", "")).strip()
            or _heuristic_feedback(metrics)["content"],
            "score": float(parsed.get("score", 0) or 0),
            "suggestions": [str(s) for s in parsed.get("suggestions", [])][:5],
        }
    except Exception as exc:
        logger.info("Ollama unavailable, using heuristic feedback: %s", exc)
        return _heuristic_feedback(metrics)
