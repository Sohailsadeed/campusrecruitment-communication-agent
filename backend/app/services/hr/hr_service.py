"""HR interview state machine managing multi-question behavioral progression."""
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.services.hr.question_bank import (
    get_next_hr_question,
    get_initial_hr_question,
)

logger = logging.getLogger(__name__)


def pick_next_hr_question(
    track: str,
    company: Optional[str],
    questions_asked: List[Dict[str, Any]],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Pick next behavioral question querying the database, avoiding duplicates and rotating tracks."""
    asked_texts = [q.get("text", "") for q in questions_asked if q.get("text")]
    chosen = get_next_hr_question(
        db=db,
        asked_texts=asked_texts,
        preferred_track=track if track != "standard_hr" else None,
    )

    if not chosen:
        q_index = len(questions_asked)
        return {
            "id": f"hr_q{q_index + 1}",
            "track": track,
            "text": "Reflecting on your past experiences, what is one professional habit or mindset you developed that most sets you apart?",
            "rubric": {
                "green_flags": ["Clear STAR structure", "Quantified personal ownership"],
                "red_flags": ["Vague claims", "Passive language"],
            },
        }

    text = chosen["text"]
    if chosen.get("track") in ("Culture Fit", "Motivation") and company:
        text = text.replace("our company", company).replace("the company", company)

    return {
        "id": chosen["id"],
        "track": chosen["track"],
        "text": text,
        "difficulty": chosen.get("difficulty", "Medium"),
        "source_type": chosen.get("source_type", "Behavioral"),
        "keywords": chosen.get("keywords", []),
        "rubric": chosen.get("rubric", {}),
    }
