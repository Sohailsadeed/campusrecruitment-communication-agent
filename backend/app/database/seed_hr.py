"""Seed canonical HR & Behavioral interview questions into PostgreSQL database."""
import json
import logging
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.hr import HRQuestion

logger = logging.getLogger("speakflow.seed_hr")

QUESTIONS_JSON_PATH = Path(__file__).resolve().parent.parent / "services" / "hr" / "hr_questions.json"


def seed_hr_questions(db: Session) -> int:
    """Ensure all deduplicated HR questions from hr_questions.json are populated in database."""
    try:
        existing_count = db.scalar(select(func.count()).select_from(HRQuestion)) or 0
        if existing_count > 0:
            logger.info("HR question bank already populated (%d questions in database)", existing_count)
            return existing_count

        if not QUESTIONS_JSON_PATH.exists():
            logger.warning("hr_questions.json not found at %s", QUESTIONS_JSON_PATH)
            return 0

        with open(QUESTIONS_JSON_PATH, "r", encoding="utf-8") as f:
            questions_data = json.load(f)

        count = 0
        for item in questions_data:
            q_text = item.get("question", "").strip()
            if not q_text:
                continue

            # Verify uniqueness just in case
            exists = db.scalar(select(HRQuestion.id).where(HRQuestion.question_text == q_text).limit(1))
            if exists:
                continue

            hr_q = HRQuestion(
                question_key=item.get("id", f"hr_q{count+1:02d}"),
                question_text=q_text,
                category=item.get("category", "General"),
                difficulty=item.get("difficulty", "Medium"),
                source_type=item.get("source_type", "Behavioral"),
                keywords=item.get("keywords", []),
                rubric=item.get("rubric", {}),
            )
            db.add(hr_q)
            count += 1

        db.commit()
        logger.info("Successfully seeded %d canonical HR questions into database.", count)
        return count
    except Exception as exc:
        db.rollback()
        logger.error("Failed to seed HR questions into database: %s", exc)
        return 0
