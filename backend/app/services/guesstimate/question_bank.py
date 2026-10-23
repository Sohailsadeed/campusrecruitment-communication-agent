"""Question bank service loading and querying curated guesstimate problems."""
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Canonical category mapping
CATEGORY_ALIASES = {
    "market sizing": "Market Sizing",
    "revenue": "Revenue Estimation",
    "revenue estimation": "Revenue Estimation",
    "operations": "Operational & Capacity Sizing",
    "operational": "Operational & Capacity Sizing",
    "operational & capacity sizing": "Operational & Capacity Sizing",
    "operational & capacity": "Operational & Capacity Sizing",
    "abstract": "Abstract / Fermi Problems",
    "fermi": "Abstract / Fermi Problems",
    "abstract / fermi problems": "Abstract / Fermi Problems",
}

CANONICAL_CATEGORIES = [
    "Market Sizing",
    "Revenue Estimation",
    "Operational & Capacity Sizing",
    "Abstract / Fermi Problems",
]

DIFFICULTY_LEVELS = ["Beginner", "Intermediate", "Advanced"]

_cached_questions: Optional[List[Dict[str, str]]] = None


def normalize_category(raw_cat: str) -> str:
    """Normalize raw category string into canonical label."""
    if not raw_cat:
        return "Market Sizing"
    cleaned = raw_cat.strip().lower()
    return CATEGORY_ALIASES.get(cleaned, raw_cat.strip())


def get_all_questions() -> List[Dict[str, str]]:
    """Load and cache all 990 curated questions from guesstimate.json."""
    global _cached_questions
    if _cached_questions is not None:
        return _cached_questions

    json_path = Path(__file__).resolve().parent.parent.parent.parent / "guesstimate.json"
    if not json_path.exists():
        # Fallback check in current dir
        json_path = Path("guesstimate.json").resolve()

    if not json_path.exists():
        logger.warning("guesstimate.json not found at %s. Using default fallback questions.", json_path)
        _cached_questions = [
            {
                "question": "Estimate the annual number of laptops purchased by college students in India.",
                "category": "Market Sizing",
                "difficulty": "Intermediate",
            },
            {
                "question": "Estimate the daily revenue of a busy Starbucks store in central Manhattan.",
                "category": "Revenue Estimation",
                "difficulty": "Intermediate",
            },
            {
                "question": "Estimate the number of commercial flights departing from Heathrow Airport in 24 hours.",
                "category": "Operational & Capacity Sizing",
                "difficulty": "Advanced",
            },
            {
                "question": "Estimate the number of piano tuners in the city of Chicago.",
                "category": "Abstract / Fermi Problems",
                "difficulty": "Intermediate",
            },
        ]
        return _cached_questions

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        normalized = []
        for item in raw_data:
            q = (item.get("question") or "").strip()
            cat = normalize_category(item.get("category", ""))
            diff = (item.get("difficulty") or "Intermediate").strip().capitalize()
            if diff not in DIFFICULTY_LEVELS:
                diff = "Intermediate"
            if q:
                normalized.append({
                    "question": q,
                    "category": cat,
                    "difficulty": diff,
                })

        _cached_questions = normalized
        logger.info("Successfully loaded %d guesstimate questions.", len(_cached_questions))
        return _cached_questions
    except Exception as exc:
        logger.error("Failed to parse guesstimate.json: %s", exc)
        return []


def get_metadata_summary() -> Dict[str, Any]:
    """Return categories and difficulties breakdown and total counts."""
    questions = get_all_questions()
    cat_counts: Dict[str, int] = {cat: 0 for cat in CANONICAL_CATEGORIES}
    diff_counts: Dict[str, int] = {diff: 0 for diff in DIFFICULTY_LEVELS}

    for item in questions:
        cat = item["category"]
        diff = item["difficulty"]
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        diff_counts[diff] = diff_counts.get(diff, 0) + 1

    return {
        "total_questions": len(questions),
        "categories": [
            {
                "id": cat,
                "label": cat,
                "count": cat_counts.get(cat, 0),
            }
            for cat in CANONICAL_CATEGORIES
        ],
        "difficulties": [
            {
                "id": diff,
                "label": diff,
                "count": diff_counts.get(diff, 0),
            }
            for diff in DIFFICULTY_LEVELS
        ],
    }


def get_random_question(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    exclude: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Retrieve a random curated question matching category & difficulty."""
    questions = get_all_questions()
    if not questions:
        return {
            "question": "Estimate the daily number of coffees sold in Tokyo.",
            "category": "Market Sizing",
            "difficulty": "Intermediate",
        }

    norm_cat = normalize_category(category) if category and category.lower() != "all" else None
    norm_diff = difficulty.capitalize() if difficulty and difficulty.lower() != "all" else None
    exclude_set = set(exclude or [])

    filtered = [
        q for q in questions
        if (norm_cat is None or q["category"] == norm_cat)
        and (norm_diff is None or q["difficulty"] == norm_diff)
        and q["question"] not in exclude_set
    ]

    if not filtered:
        # Relax difficulty if no exact matches found with exclusion
        filtered = [
            q for q in questions
            if norm_cat is None or q["category"] == norm_cat
        ]

    if not filtered:
        filtered = questions

    return random.choice(filtered)
