"""HR interview state machine managing multi-question behavioral progression."""
import logging
from typing import Any, Dict, List, Optional

from app.services.hr.evaluator import evaluate_hr_answer, generate_hr_report
from app.services.hr.question_bank import (
    HR_QUESTIONS,
    get_curated_hr_questions,
    get_initial_hr_question,
)

logger = logging.getLogger(__name__)

STANDARD_ROTATION_TRACKS = [
    "leadership_ownership",
    "conflict_resilience",
    "failure_adaptability",
    "culture_motivation",
    "ambiguity_prioritization",
]


def pick_next_hr_question(
    track: str,
    company: Optional[str],
    questions_asked: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Pick next behavioral question avoiding duplicates and rotating tracks if standard."""
    asked_texts = {q.get("text", "") for q in questions_asked}
    q_index = len(questions_asked)

    if track == "standard_hr":
        # Rotate through tracks
        target_track = STANDARD_ROTATION_TRACKS[q_index % len(STANDARD_ROTATION_TRACKS)]
        candidates = [q for q in HR_QUESTIONS if q["track"] == target_track and q["text"] not in asked_texts]
        if not candidates:
            candidates = [q for q in HR_QUESTIONS if q["text"] not in asked_texts]
    else:
        candidates = [q for q in HR_QUESTIONS if q["track"] == track and q["text"] not in asked_texts]
        if not candidates:
            candidates = [q for q in HR_QUESTIONS if q["text"] not in asked_texts]

    if not candidates:
        return {
            "id": f"hr_q{q_index + 1}",
            "track": track,
            "text": "Reflecting on your past experiences, what is one professional habit or mindset you developed that most sets you apart?",
        }

    chosen = candidates[0]
    # Customize if culture question has company name
    text = chosen["text"]
    if chosen["track"] == "culture_motivation" and company:
        text = text.replace("our engineering team", f"the engineering team at {company}").replace("our company", company)

    return {
        "id": chosen["id"],
        "track": chosen["track"],
        "text": text,
        "rubric": chosen.get("rubric", {}),
    }
