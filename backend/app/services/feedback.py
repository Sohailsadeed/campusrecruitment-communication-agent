"""JAM & Multimodal LLM-backed feedback evaluation via Ollama."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import requests

from config import settings

logger = logging.getLogger(__name__)


FEEDBACK_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "score": {"type": "number"},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "congruence": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "analysis": {"type": "string"},
            },
            "required": ["status", "analysis"],
        },
        "avatar_reaction": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "gesture": {"type": "string"},
                "timing": {"type": "string"},
            },
            "required": ["expression", "gesture"],
        },
        "rewrites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string"},
                    "original": {"type": "string"},
                    "polish": {"type": "string"},
                    "grade": {"type": "string"},
                    "polish_grade": {"type": "string"},
                    "tip": {"type": "string"},
                },
                "required": ["original", "polish", "tip"],
            },
        },
        "competencies": {
            "type": "object",
            "properties": {
                "articulation": {"type": "integer"},
                "structure": {"type": "integer"},
                "technical_depth": {"type": "integer"},
                "pacing": {"type": "integer"},
                "confidence": {"type": "integer"},
                "conciseness": {"type": "integer"},
            },
            "required": [
                "articulation",
                "structure",
                "technical_depth",
                "pacing",
                "confidence",
                "conciseness",
            ],
        },
        "mastery_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        },
        "curated_drills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "desc": {"type": "string"},
                    "duration": {"type": "string"},
                    "icon": {"type": "string"},
                },
                "required": ["title", "desc"],
            },
        },
    },
    "required": ["content", "score", "suggestions", "congruence", "competencies", "rewrites"],
}


PROMPT_TEMPLATE = """You are an expert Chief Adjudicator & Executive Communication Coach for high-stakes interviews and speaking rounds.
The speaker chose this specific topic/drill: "{topic}"

Speech & Acoustic Analytics:
- Selected Topic: "{topic}"
- Speaking pace: {speaking_pace} WPM
- Total Silence/Pause Time: {total_pause_time}s across {pause_count} pauses (longest pause: {longest_pause}s)
- Hesitations / Filler sounds count: {filler_count} ({filler_list})
- Repeated content words: {repetition_count} ({repetition_list})
- Calculated Score: {jam_score}/100 | Verdict: {jam_verdict}

Acoustic Prosody & Vocal Dynamics (Physical Soundwave Analysis):
- Acoustic Confidence Score: {prosody_confidence}/100
- Vocal Energy Projection: {vocal_energy_db} dB (RMS power)
- Tone Verdict: {tone_verdict}
- Terminal Intonation: {terminal_drops} decisive downward drop(s), {uptalks} hesitant uptalk inflection(s)
- Dynamic Pitch Modulation Score: {modulation_score}/100

Visual & Nonverbal Signals (MediaPipe Utterance Tracking):
- Overall Eye Contact Consistency: {eye_contact_percentage}%
- Posture & Presence Score: {posture_quality}%
- Hand Gestures / Open Emphasis Count: {hand_gestures_count}
- Hand-to-Face / Fidget Events: {fidget_count}
- Utterance-Aligned Multimodal Evidence:
{multimodal_evidence}

Transcript:
"{transcript}"

As the Chief Coach:
1. Deliver a concise 3-5 sentence adjudication addressing topic delivery, verbal clarity, nonverbal presence, and flow.
2. Evaluate Verbal-Nonverbal Congruence: Determine whether the candidate's body posture, gestures, and presence matched their spoken intent.
3. Select 1 or 2 specific weak phrases/sentences from the transcript (especially where filler words, vagueness, or repetition occurred) and provide executive-level "Critical Moment Rewrites" side-by-side with original vs polished version, letter grades, and actionable tips.
4. Score the 6 Core Competency Vectors (0-100 each):
   - Articulation & Acoustic Clarity
   - Structure & STAR Logic Flow
   - Technical Depth & Precision
   - Pacing & Strategic Pauses
   - Confidence & Assertive Tone (IMPORTANT: Base Confidence & Tone strictly on physical vocal dynamics, energy, and decisive terminal intonation — completely decoupled from eye contact)
   - Conciseness (Low Fluff)
5. Highlight 2-3 observed mastery points, 2 curated follow-up drills, and an Avatar Nonverbal Reaction Plan (e.g. empathic_nod, attentive_tilt, open_palm).

Respond ONLY with a JSON object adhering to the schema.
"""


def _build_prompt(
    metrics: Dict[str, Any],
    transcript: str,
    topic: str = "General Topic",
    prosody_metrics: Optional[Dict[str, Any]] = None,
) -> str:
    fillers = metrics.get("filler_words_list") or {}
    clean_fillers = {k: v for k, v in fillers.items() if k != "_jam"}
    filler_list = ", ".join(f"{k} x{v}" for k, v in clean_fillers.items()) or "none"

    reps = metrics.get("repeated_words") or {}
    rep_list = ", ".join(f"'{k}' x{v}" for k, v in reps.items()) or "none"

    excerpt = (transcript or "").strip()
    if len(excerpt) > 800:
        excerpt = excerpt[:800] + "..."

    prosody = prosody_metrics or metrics.get("prosody") or {}

    timeline = metrics.get("multimodal_timeline") or []
    timeline_lines = []
    for item in timeline[:4]:
        u_id = item.get("utterance_id", 1)
        face = item.get("face", {})
        gesture = item.get("gesture", {})
        expr = face.get("dominant_expression", "neutral")
        ec = face.get("eye_contact_ratio", 0.8)
        posture = gesture.get("posture", "upright")
        events = ", ".join(gesture.get("events", ["none"]))
        timeline_lines.append(
            f"  * Utterance {u_id} [{item.get('start', 0)}s - {item.get('end', 0)}s]: "
            f"Expression={expr}, EyeContact={int(ec*100)}%, Posture={posture}, Gestures=[{events}]"
        )
    multimodal_evidence = "\n".join(timeline_lines) if timeline_lines else "  * Stable upright presence with consistent delivery."

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
        prosody_confidence=prosody.get("confidence_score", 84.0),
        vocal_energy_db=prosody.get("vocal_energy_db", -22.0),
        tone_verdict=prosody.get("tone_verdict", "Measured & Structured"),
        terminal_drops=prosody.get("terminal_drop_count", 2),
        uptalks=prosody.get("uptalk_count", 0),
        modulation_score=prosody.get("pitch_modulation_score", 88.0),
        eye_contact_percentage=metrics.get("eye_contact_percentage", 82.0),
        posture_quality=metrics.get("posture_quality", 85.0),
        hand_gestures_count=metrics.get("hand_gestures_count", 2),
        fidget_count=metrics.get("fidget_count", 0),
        multimodal_evidence=multimodal_evidence,
        transcript=excerpt,
    )


def _heuristic_feedback(
    metrics: Dict[str, Any],
    topic: str = "Impromptu Speech",
    transcript: str = "",
    prosody_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministic fallback feedback with VerbalIQ rewrites, competencies, and multimodal congruence."""
    pace = float(metrics.get("speaking_pace") or 0)
    fillers = int(metrics.get("filler_words_count") or 0)
    reps = int(metrics.get("repetitions_count") or 0)
    pauses = float(metrics.get("total_pause_time") or 0.0)
    longest_pause = float(metrics.get("longest_pause") or 0.0)
    score = float(metrics.get("jam_score", metrics.get("clarity_score", 78.0)) or 78.0)
    verdict = str(metrics.get("jam_verdict") or "Qualified")
    ec = float(metrics.get("eye_contact_percentage") or 82.0)
    fidgets = int(metrics.get("fidget_count") or 0)

    prosody = prosody_metrics or metrics.get("prosody") or {}

    parts: List[str] = [f"Adjudication for topic '{topic}': Verdict is {verdict} ({score:.0f}/100)."]
    suggestions: List[str] = []

    # Calculate 6-axis competencies
    base_art = min(96, max(65, int(score + 4)))
    base_struct = min(94, max(60, int(score + (2 if reps == 0 else -6))))
    base_tech = min(92, max(65, int(score + 3)))
    base_pace = min(95, max(58, int(92 - abs(pace - 145) * 0.6)))

    # Confidence is 100% derived from acoustic soundwave prosody (decoupled from eye contact / video)
    if "confidence_score" in prosody:
        base_conf = int(round(float(prosody["confidence_score"])))
    else:
        # Fallback acoustic confidence based solely on pauses and vocal flow, WITHOUT eye contact or fidgets
        base_conf = min(96, max(60, int(score - (4 if longest_pause > 2.0 else 0) - (3 if pauses > 4.0 else 0))))

    base_concise = min(94, max(50, int(90 - fillers * 5 - reps * 4)))

    competencies = {
        "articulation": base_art,
        "structure": base_struct,
        "technical_depth": base_tech,
        "pacing": base_pace,
        "confidence": base_conf,
        "conciseness": base_concise,
    }

    if ec >= 80 and fidgets == 0:
        congruence = {
            "status": "High Alignment",
            "analysis": f"Strong nonverbal presence reinforced spoken claims with steady posture.",
        }
    else:
        congruence = {
            "status": "Mild Incongruence",
            "analysis": f"Observed minor hesitation cues ({fidgets} touch/fidget events, {ec:.0f}% gaze consistency) during complex arguments.",
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
        suggestions.append(f"Maintain direct screen eye contact when summarizing strategic takeaways for '{topic}'.")

    # Generate Critical Moment Rewrites
    rewrites = []
    text_clean = (transcript or "").strip()
    sentences = [s.strip() for s in text_clean.split(".") if len(s.strip().split()) >= 3]

    weak_sentence = next(
        (s for s in sentences if any(f in s.lower() for f in ["basically", "like", "you know", "um", "uh", "so a", "pace and", "our place"])),
        sentences[0] if sentences else None
    )

    if weak_sentence:
        # Detect topic context for targeted executive polish
        lower_s = weak_sentence.lower()
        lower_topic = (topic or "").lower()

        if any(w in lower_s for w in ["student", "college", "university", "institute", "year", "pursuing", "degree"]):
            # Student / Self-Introductory Polish
            polished_ver = "I am a pre-final year engineering student at the Institute of Technology, specializing in building distributed software systems and high-throughput backend applications."
            tip = "Eliminate casual conversational qualifiers ('Okay, currently...') and immediately anchor your introduction with your academic discipline and core engineering focus."
        elif "communication" in lower_s or "communication" in lower_topic or "work" in lower_s:
            polished_ver = "Effective communication plays a critical role in the workplace, aligning cross-functional teams and technical stakeholders across modern IT organizations to maintain operational clarity."
            tip = "Eliminate conversational openers ('So a...') and fragmented syntax. Lead with an authoritative thesis ('Effective communication plays a critical role...') and state the concrete organizational impact."
        elif "system" in lower_topic or "technical" in lower_topic or "scale" in lower_s or "backend" in lower_s or "develop" in lower_s:
            polished_ver = "To eliminate latency bottlenecks under peak concurrency, we decoupled the ingestion tier using partitioned message queues, driving a 40% gain in pipeline throughput."
            tip = "Replace descriptive colloquialisms with architectural specifics and quantified performance outcomes."
        else:
            # Clean natural polish without robotic hallucinated templates
            cleaned_core = weak_sentence
            for fl in ["basically", "you know", "like", "um", "uh", "so a ", "so, ", "well, ", "okay, ", "okay "]:
                cleaned_core = re.sub(r"\b" + re.escape(fl) + r"\b", "", cleaned_core, flags=re.IGNORECASE)
            cleaned_core = " ".join(cleaned_core.split()).strip()
            if cleaned_core:
                cleaned_core = cleaned_core[0].upper() + cleaned_core[1:]
            polished_ver = f"{cleaned_core}. Specifically, our primary objective was delivering reliable technical execution with high cross-team alignment."
            tip = "Lead with direct assertive phrasing, eliminating conversational qualifiers and hesitation words."

        rewrites.append({
            "timestamp": "00:14",
            "original": f'"{weak_sentence}."',
            "polish": f'"{polished_ver}"',
            "grade": "C-",
            "polish_grade": "A+",
            "tip": tip,
        })
    else:
        rewrites.append({
            "timestamp": "00:18",
            "original": f'"{text_clean[:60]}..."',
            "polish": f'"Specifically regarding {topic}, we structured our approach around measurable deliverables, achieving high cross-team alignment."',
            "grade": "B",
            "polish_grade": "A+",
            "tip": "Ground strategic statements with concrete milestones and architectural specifics."
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
        "congruence": congruence,
        "avatar_reaction": {
            "expression": "empathic_nod" if score >= 75 else "attentive_focus",
            "gesture": "open_palm_welcome" if score >= 75 else "supportive_tilt",
            "timing": "00:02"
        },
        "rewrites": rewrites,
        "competencies": competencies,
        "mastery_points": mastery_points,
        "curated_drills": curated_drills,
    }


def generate_feedback(
    metrics: Dict[str, Any],
    transcript: str,
    topic: str = "Impromptu Speech",
    prosody_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate comprehensive VerbalIQ feedback with rewrites, competencies, and multimodal congruence."""
    prosody = prosody_metrics or metrics.get("prosody") or {}
    prompt = _build_prompt(metrics, transcript, topic, prosody_metrics=prosody)
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    fallback = _heuristic_feedback(metrics, topic, transcript, prosody_metrics=prosody)

    # 1. Attempt with exact JSON Schema
    for fmt in [FEEDBACK_JSON_SCHEMA, "json"]:
        try:
            response = requests.post(
                url,
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": fmt,
                    "options": {"temperature": 0.25},
                },
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            raw = data.get("response", "").strip() or data.get("thinking", "").strip()
            if not raw:
                continue
            start_idx = raw.find("{")
            end_idx = raw.rfind("}")
            if start_idx != -1 and end_idx != -1:
                raw = raw[start_idx : end_idx + 1]
            parsed = json.loads(raw)

            competencies = parsed.get("competencies") or fallback["competencies"]
            # Enforce 100% DSP acoustic confidence — completely decoupled from video/eye contact
            if "confidence_score" in prosody:
                competencies["confidence"] = int(round(float(prosody["confidence_score"])))

            return {
                "content": str(parsed.get("content", "")).strip() or fallback["content"],
                "score": float(parsed.get("score", metrics.get("jam_score", 0)) or fallback["score"]),
                "suggestions": [str(s) for s in parsed.get("suggestions", [])][:5] or fallback["suggestions"],
                "congruence": parsed.get("congruence") or fallback["congruence"],
                "avatar_reaction": parsed.get("avatar_reaction") or fallback["avatar_reaction"],
                "rewrites": parsed.get("rewrites") or fallback["rewrites"],
                "competencies": competencies,
                "mastery_points": parsed.get("mastery_points") or fallback["mastery_points"],
                "curated_drills": parsed.get("curated_drills") or fallback["curated_drills"],
            }
        except Exception as exc:
            logger.debug("Ollama format %s failed: %s", fmt, exc)
            continue

    logger.warning("Ollama unavailable at %s. Used enhanced linguistic fallback.", url)
    return fallback

