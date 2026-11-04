"""Behavioral & HR question bank with database-backed storage and rubrics."""
import json
import logging
from pathlib import Path
import random
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hr import HRQuestion

logger = logging.getLogger("speakflow.hr_question_bank")

QUESTIONS_JSON_PATH = Path(__file__).resolve().parent / "hr_questions.json"

HR_TRACKS = [
    {
        "id": "leadership",
        "title": "Leadership & Ownership",
        "icon": "military_tech",
        "desc": "Demonstrating individual initiative, mentoring, delegating, and end-to-end accountability.",
        "rubric_focus": "Evaluates 'I' vs 'we' ownership, personal conviction, task delegation, and proactive problem solving.",
    },
    {
        "id": "conflict_resolution",
        "title": "Conflict Resolution & Disagreement",
        "icon": "handshake",
        "desc": "Navigating difficult disagreements with peers, seniors, managers, or stakeholders.",
        "rubric_focus": "Evaluates emotional intelligence, active listening, de-escalation, and finding win-win objective consensus.",
    },
    {
        "id": "adaptability",
        "title": "Adaptability & Resilience",
        "icon": "restart_alt",
        "desc": "Learning new domains quickly, responding to shifting priorities, and bouncing back from mistakes.",
        "rubric_focus": "Evaluates humility, root-cause self-awareness, and concrete corrective adjustments.",
    },
    {
        "id": "team_collaboration",
        "title": "Team Collaboration & Trust",
        "icon": "groups",
        "desc": "Building trust with teammates, cross-functional synergy, and collective delivery.",
        "rubric_focus": "Evaluates interpersonal trust, credit sharing, and unblocking teammates.",
    },
    {
        "id": "culture_fit",
        "title": "Company Culture & Values",
        "icon": "domain",
        "desc": "Explaining genuine organizational fit, corporate value alignment, and team environment contributions.",
        "rubric_focus": "Evaluates depth of research into the company, value alignment, and positive team presence.",
    },
    {
        "id": "motivation",
        "title": "Motivation & Drive",
        "icon": "bolt",
        "desc": "Demonstrating intrinsic drive, perseverance through repetitive tasks, and career passion.",
        "rubric_focus": "Evaluates intrinsic drive, perseverance, and genuine enthusiasm for the discipline.",
    },
    {
        "id": "career_goals",
        "title": "Career Goals & Trajectory",
        "icon": "trending_up",
        "desc": "Articulating long-term aspirations, desired skill development, and 5-year vision.",
        "rubric_focus": "Evaluates self-awareness, ambition, and alignment with the target role.",
    },
    {
        "id": "work_style",
        "title": "Work Style & Prioritization",
        "icon": "schedule",
        "desc": "Daily task organization, remote productivity, and managing competing deadlines.",
        "rubric_focus": "Evaluates prioritization frameworks, autonomy, and structured execution.",
    },
]

# Track alias normalization map
TRACK_ALIAS_MAP = {
    "leadership_ownership": "Leadership",
    "leadership": "Leadership",
    "conflict_resilience": "Conflict Resolution",
    "conflict_resolution": "Conflict Resolution",
    "failure_adaptability": "Adaptability",
    "adaptability": "Adaptability",
    "team_collaboration": "Team Collaboration",
    "culture_motivation": "Culture Fit",
    "culture_fit": "Culture Fit",
    "motivation": "Motivation",
    "career_goals": "Career Goals",
    "work_style": "Work Style",
    "ambiguity_prioritization": "Work Style",
}


def get_hr_tracks() -> List[Dict[str, Any]]:
    """Return available behavioral interview tracks."""
    return HR_TRACKS


def normalize_category_name(raw: Optional[str]) -> Optional[str]:
    """Map frontend/backend track IDs to standard DB category names."""
    if not raw or raw in ("all", "standard_hr"):
        return None
    return TRACK_ALIAS_MAP.get(raw.lower(), raw)


def _load_fallback_questions() -> List[Dict[str, Any]]:
    """Load questions directly from JSON file if DB is not supplied."""
    if not QUESTIONS_JSON_PATH.exists():
        return []
    try:
        with open(QUESTIONS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Error reading hr_questions.json fallback: %s", exc)
        return []


def query_hr_questions(
    db: Optional[Session] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query questions from the database with category/difficulty filtering, falling back to JSON."""
    normalized_cat = normalize_category_name(category)

    if db is not None:
        try:
            stmt = select(HRQuestion)
            if normalized_cat:
                stmt = stmt.where(HRQuestion.category.ilike(f"%{normalized_cat}%"))
            if difficulty and difficulty.lower() != "all":
                stmt = stmt.where(HRQuestion.difficulty.ilike(difficulty))

            results = db.scalars(stmt).all()
            if results:
                return [
                    {
                        "id": q.question_key,
                        "track": q.category,
                        "text": q.question_text,
                        "difficulty": q.difficulty,
                        "source_type": q.source_type,
                        "keywords": q.keywords,
                        "rubric": q.rubric,
                    }
                    for q in results
                ]
        except Exception as exc:
            logger.warning("DB query for HR questions failed, falling back to JSON: %s", exc)

    # Fallback to JSON
    raw_list = _load_fallback_questions()
    filtered = []
    for item in raw_list:
        if normalized_cat and normalized_cat.lower() not in item.get("category", "").lower():
            continue
        if difficulty and difficulty.lower() != "all" and item.get("difficulty", "").lower() != difficulty.lower():
            continue
        filtered.append({
            "id": item.get("id"),
            "track": item.get("category"),
            "text": item.get("question"),
            "difficulty": item.get("difficulty"),
            "source_type": item.get("source_type"),
            "keywords": item.get("keywords", []),
            "rubric": item.get("rubric", {}),
        })

    return filtered if filtered else [
        {
            "id": item.get("id"),
            "track": item.get("category"),
            "text": item.get("question"),
            "difficulty": item.get("difficulty"),
            "source_type": item.get("source_type"),
            "keywords": item.get("keywords", []),
            "rubric": item.get("rubric", {}),
        }
        for item in raw_list
    ]


def get_initial_hr_question(
    db: Optional[Session] = None,
    track: str = "standard_hr",
    company: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve an initial opening question from the database."""
    questions = query_hr_questions(db=db, category=track)
    if not questions:
        # Emergency default
        return {
            "id": "hr_q_default",
            "track": "Leadership",
            "text": "Tell me about a time you led a project or team, highlighting your specific role and the outcome.",
            "rubric": {
                "green_flags": ["Clear STAR structure", "Active 'I' ownership", "Measurable result"],
                "red_flags": ["Vague narrative", "Passive language", "Missing impact"],
            },
        }

    # If company is specified and asking about culture/motivation, customize greeting prompt
    normalized = normalize_category_name(track)
    if normalized in ("Culture Fit", "Motivation") and company:
        for q in questions:
            if "company" in q["text"].lower() or "values" in q["text"].lower():
                return {
                    **q,
                    "text": q["text"].replace("our company", company).replace("this role", f"the {company} role"),
                }

    return random.choice(questions)


def get_next_hr_question(
    db: Optional[Session] = None,
    asked_texts: Optional[List[str]] = None,
    preferred_track: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Pick the next question from the DB that has not yet been asked in this session."""
    asked_set = set(t.strip().lower() for t in (asked_texts or []))
    candidates = query_hr_questions(db=db, category=preferred_track)
    unasked = [q for q in candidates if q["text"].strip().lower() not in asked_set]

    if unasked:
        return random.choice(unasked)

    # If all in preferred track were asked, draw from all remaining DB questions
    all_questions = query_hr_questions(db=db)
    all_unasked = [q for q in all_questions if q["text"].strip().lower() not in asked_set]
    if all_unasked:
        return random.choice(all_unasked)

    return None


def get_curated_hr_questions(track: Optional[str] = None) -> List[Dict[str, Any]]:
    """Backwards-compatible getter for question list."""
    return query_hr_questions(category=track)


# Backwards compatibility export
HR_QUESTIONS = query_hr_questions()

