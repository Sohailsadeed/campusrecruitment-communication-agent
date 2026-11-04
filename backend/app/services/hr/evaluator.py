"""HR & Behavioral interview evaluator; the LLM provider is chosen by configuration, local by default."""
import logging
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.services import llm_client

logger = logging.getLogger(__name__)

_llm = None
_cached_signature = None

# The HR round reads answers in one shape, so one temperature and one answer budget serve every
# question in it.
CLIENT_TEMPERATURE = 0.6
CLIENT_MAX_TOKENS = 2500


def _get_llm():
    """Return this round's chat client, built from the shared provider decision.

    The selection rule lives in `app.services.llm_client`: configuration picks the provider, a
    credential never does, and an unavailable local model is an error rather than a remote request.
    """
    global _llm, _cached_signature
    signature = llm_client.cache_signature()
    if _llm is None or _cached_signature != signature:
        _cached_signature = signature
        _llm = llm_client.build_chat_client("HR Evaluator", temperature=CLIENT_TEMPERATURE,
                                            max_tokens=CLIENT_MAX_TOKENS)
    return _llm


# ---------------------------------------------------------
# Schemas for LangChain Output Parsers
# ---------------------------------------------------------
class StarComponent(BaseModel):
    present: bool = Field(description="Was this component covered in the candidate's response?")
    summary: str = Field(description="Brief extracted summary of what the candidate stated for this component")


class StarStructureSchema(BaseModel):
    situation: StarComponent = Field(description="Situation context and background")
    task: StarComponent = Field(description="Defined goal or assignment")
    action: StarComponent = Field(description="Specific steps taken")
    result: StarComponent = Field(description="Concrete outcome, metrics, or impact")
    completeness_score: int = Field(default=75, description="STAR structural completeness from 0 to 100")
    structure_critique: str = Field(default="Good STAR structure.", description="Critique on STAR structure completeness")


class HRAnswerEvaluationSchema(BaseModel):
    overall_score: int = Field(
        default=75,
        description="Overall behavioral answer score from 0 to 100",
    )
    # STAR Breakdown (Separated from answer quality)
    star_structure: StarStructureSchema = Field(
        default_factory=StarStructureSchema,
        description="STAR completeness breakdown",
    )
    # Answer Quality & Substance Metrics
    personal_ownership_score: int = Field(
        default=75,
        description="Score from 0 to 100 on personal accountability and 'I' vs 'we' agency",
    )
    ownership_critique: str = Field(
        default="Demonstrated personal agency.",
        description="Analysis of where candidate took direct ownership vs. deflected to the team",
    )
    specificity_score: int = Field(
        default=75,
        description="Score from 0 to 100 measuring concrete details, technologies, and metrics vs. vague fluff",
    )
    specificity_critique: str = Field(
        default="Provided good specific context.",
        description="Feedback on technical and behavioral specificity",
    )
    relevance_score: int = Field(
        default=80,
        description="Score from 0 to 100 evaluating how directly the candidate answered the core prompt and demonstrated cultural maturity",
    )
    relevance_critique: str = Field(
        default="Directly addressed the prompt.",
        description="Feedback on question alignment and culture fit",
    )
    coaching_feedback: str = Field(
        default="Strong response.",
        description="Constructive advice on how the candidate can elevate this story for campus placement interviews",
    )
    ideal_star_script: str = Field(
        default="",
        description="An exemplary 45-60 second verbal delivery script showing how a top-tier candidate would articulate this answer",
    )
    # Declared, not appended: these two travel with every score so a stored evaluation can say
    # whether a model read the answer. They are set by the code, never trusted from the model.
    evaluator_basis: str = Field(
        default="fallback",
        description="Set by the service, not by the model: 'model', 'fallback' or 'heuristic'",
    )
    evaluator_error: Optional[str] = Field(
        default=None,
        description="Why the score is not a model reading of the answer, when it is not",
    )


class HRReportSchema(BaseModel):
    total_score: int = Field(default=75, description="Overall HR behavioral readiness score from 0 to 100")
    avg_ownership_score: int = Field(default=75, description="Average personal ownership and initiative score (0-100)")
    avg_star_completeness: int = Field(default=80, description="Average STAR structure completeness score (0-100)")
    avg_specificity_score: int = Field(default=75, description="Average detail and concrete impact score (0-100)")
    strengths: List[str] = Field(default_factory=list, description="Top behavioral and communication strengths demonstrated")
    weaknesses: List[str] = Field(default_factory=list, description="High-priority coaching areas for placement day")
    executive_summary: str = Field(default="", description="Executive assessment of candidate's behavioral poise, cultural maturity, and hire readiness")
    report_basis: str = Field(
        default="empirical",
        description="Set by the service: 'model' when a model wrote the prose, 'empirical' when only the arithmetic did",
    )
    report_error: Optional[str] = Field(
        default=None,
        description="Why the narrative is the standard wording rather than a synthesis of this candidate's round",
    )
    answers_not_model_scored: int = Field(
        default=0,
        description="How many of this round's answers were never read by a model",
    )


# ---------------------------------------------------------
# Prompts
# ---------------------------------------------------------
_hr_eval_parser = JsonOutputParser(pydantic_object=HRAnswerEvaluationSchema)
_hr_eval_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert HR Director and Behavioral Interview Coach at a top global technology company, "
            "evaluating a student candidate's verbal response to a behavioral interview question.\n\n"
            "CRITICAL EVALUATION PRINCIPLE:\n"
            "- Strictly distinguish between STAR COMPLETENESS and ANSWER SUBSTANCE.\n"
            "- A student can mechanically mention all 4 STAR parts and STILL give a weak, vague answer lacking personal ownership.\n\n"
            "EVALUATION CRITERIA:\n"
            "1. STAR STRUCTURE COMPLETENESS (0-100):\n"
            "- Did they clearly cover: Situation (context), Task (objective), Action (specific steps), Result (measurable impact)?\n"
            "- Set present=true/false and summarize what was said for each.\n\n"
            "2. PERSONAL OWNERSHIP & AGENCY (0-100) — CRUCIAL:\n"
            "- Did the candidate say 'I investigated', 'I drafted', 'I decided'—showing personal accountability?\n"
            "- Or did they hide behind passive group language ('we built', 'the team kind of decided') without clarifying their individual contribution?\n\n"
            "3. SPECIFICITY & EVIDENCE (0-100):\n"
            "- Did they provide concrete details (metrics, timelines, technical trade-offs, interpersonal dialogue)?\n"
            "- Or was it vague generalities and cliché fluff ('we worked hard and delivered on time')?\n\n"
            "4. RELEVANCE & CULTURE FIT (0-100):\n"
            "- Did the story actually answer the interviewer's prompt?\n"
            "- Does the story show professional maturity, emotional intelligence, and resilience under pressure?\n\n"
            "5. IDEAL 45-60s STAR SCRIPT:\n"
            "- Write an exemplary, high-impact verbal script demonstrating how a star candidate would tell this story concisely.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Target Role: {role}\n"
            "Target Company: {company}\n"
            "Interview Track: {track}\n"
            "Behavioral Question: {question}\n\n"
            "Candidate's Response:\n"
            "\"\"\"\n{candidate_answer}\n\"\"\"\n\n"
            "Evaluate the response thoroughly and return structured behavioral feedback.",
        ),
    ]
)

_hr_report_parser = JsonOutputParser(pydantic_object=HRReportSchema)
_hr_report_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a Senior Talent Partner compiling a comprehensive Behavioral Interview Scorecard for a campus candidate.\n"
            "Synthesize total score (0-100), average personal ownership score (0-100), average STAR completeness (0-100), average specificity (0-100), key behavioral strengths, areas for improvement, and an executive hiring recommendation.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Target Role: {role}\n"
            "Target Company: {company}\n"
            "Completed Questions & Evaluations:\n{questions_summary}\n\n"
            "Generate the final behavioral assessment dossier.",
        ),
    ]
)


async def evaluate_hr_answer(
    role: str,
    company: Optional[str],
    track: str,
    question: str,
    candidate_answer: str,
) -> Dict[str, Any]:
    """Evaluate candidate's behavioral answer across STAR completeness and substance."""
    default_fallback: Dict[str, Any] = {
        "overall_score": 74,
        "star_structure": {
            "situation": {"present": True, "summary": "Provided project background."},
            "task": {"present": True, "summary": "Outlined the primary objective."},
            "action": {"present": True, "summary": "Described execution steps."},
            "result": {"present": True, "summary": "Mentioned the outcome."},
            "completeness_score": 75,
            "structure_critique": "Solid STAR framework followed.",
        },
        "personal_ownership_score": 72,
        "ownership_critique": "Good individual initiative mentioned; use more direct 'I' statements to highlight personal decisions.",
        "specificity_score": 75,
        "specificity_critique": "Concrete context provided; quantify the final business or user impact where possible.",
        "relevance_score": 78,
        "relevance_critique": "Answer was well-aligned with the interview prompt.",
        "coaching_feedback": "Focus on clearly articulating your personal agency and quantifying the end result.",
        "ideal_star_script": (
            "When facing this challenge, my task was to ensure on-time delivery while maintaining quality. "
            "I took personal ownership by auditing the workflow, facilitating daily alignment syncs, and re-architecting the critical path. "
            "As a result, we reduced cycle time by 25% and delivered ahead of the deadline."
        ),
        # Every score has to say whether a model read the answer. Without this, the fixed 74 below is
        # indistinguishable from a mediocre real evaluation once it is stored in the session record.
        "evaluator_basis": "fallback",
        "evaluator_error": None,
    }

    if not candidate_answer or len(candidate_answer.strip()) < 15:
        default_fallback["overall_score"] = 40
        default_fallback["personal_ownership_score"] = 40
        default_fallback["specificity_score"] = 40
        default_fallback["coaching_feedback"] = "Answer was too brief to evaluate behavioral STAR structure or personal ownership."
        default_fallback["evaluator_basis"] = "heuristic"
        default_fallback["evaluator_error"] = "answer too brief to send for model evaluation"
        return default_fallback

    try:
        chain = _hr_eval_prompt | _get_llm() | _hr_eval_parser
        result = await chain.ainvoke(
            {
                "role": role,
                "company": company or "General Organization",
                "track": track,
                "question": question,
                "candidate_answer": candidate_answer,
                "format_instructions": _hr_eval_parser.get_format_instructions(),
            }
        )

        # A small local model sometimes returns the JSON *schema* from the format instructions instead
        # of an instance of it. That parses cleanly and carries no scores, so it must not be silently
        # defaulted to 75/80 and reported as the candidate's evaluation.
        if not isinstance(result, dict) or result.get("overall_score") is None:
            raise ValueError(
                f"model produced no overall_score (got {type(result).__name__} with keys "
                f"{sorted(result)[:5] if isinstance(result, dict) else repr(result)[:80]})"
            )

        overall = int(result.get("overall_score"))
        ownership = int(result.get("personal_ownership_score", 75))
        specificity = int(result.get("specificity_score", 75))
        relevance = int(result.get("relevance_score", 80))

        star = result.get("star_structure")
        star_was_default = not isinstance(star, dict) or not star
        if star_was_default:
            star = default_fallback["star_structure"]

        return {
            "overall_score": max(0, min(100, overall)),
            "star_structure": star,
            "personal_ownership_score": max(0, min(100, ownership)),
            "ownership_critique": str(result.get("ownership_critique") or default_fallback["ownership_critique"]),
            "specificity_score": max(0, min(100, specificity)),
            "specificity_critique": str(result.get("specificity_critique") or default_fallback["specificity_critique"]),
            "relevance_score": max(0, min(100, relevance)),
            "relevance_critique": str(result.get("relevance_critique") or default_fallback["relevance_critique"]),
            "coaching_feedback": str(result.get("coaching_feedback") or default_fallback["coaching_feedback"]),
            "ideal_star_script": str(result.get("ideal_star_script") or default_fallback["ideal_star_script"]),
            "evaluator_basis": "model",
            "evaluator_error": (
                "model gave no star_structure; the STAR breakdown shown is the placeholder, not a reading of the answer"
                if star_was_default else None
            ),
        }
    except Exception as exc:
        logger.warning("HR answer evaluation error: %s. Using structured fallback.", exc, exc_info=True)
        default_fallback["evaluator_error"] = f"{type(exc).__name__}: {exc}"[:300]
        return default_fallback


async def generate_hr_report(
    role: str,
    company: Optional[str],
    questions_asked: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate final comprehensive HR behavioral scorecard."""
    default_fallback: Dict[str, Any] = {
        "total_score": 76,
        "avg_ownership_score": 75,
        "avg_star_completeness": 78,
        "avg_specificity_score": 74,
        "strengths": [
            "Demonstrated strong personal initiative and structured thinking.",
            "Consistently applied the STAR framework across responses.",
        ],
        "weaknesses": [
            "Emphasize personal 'I' agency over collective 'we' narrative in team scenarios.",
            "Back up qualitative achievements with quantitative results.",
        ],
        "executive_summary": (
            "Candidate demonstrated strong cultural maturity and structured communication. "
            "With slightly sharper quantitative impact framing, they will stand out in Tier-1 behavioral rounds."
        ),
        # The averages below are arithmetic, but the strengths/weaknesses/summary prose is not: say
        # which of the two the reader is looking at, and how many per-answer scores were placeholders.
        "report_basis": "heuristic",
        "report_error": None,
        "answers_not_model_scored": 0,
    }

    if not questions_asked:
        return default_fallback

    not_model_scored = sum(
        1 for q in questions_asked if (q.get("evaluation") or {}).get("evaluator_basis") not in (None, "model")
    )

    # Pre-compute empirical averages
    ownership_scores = [q.get("evaluation", {}).get("personal_ownership_score", 75) for q in questions_asked]
    star_scores = [q.get("evaluation", {}).get("star_structure", {}).get("completeness_score", 75) for q in questions_asked]
    spec_scores = [q.get("evaluation", {}).get("specificity_score", 75) for q in questions_asked]
    overall_scores = [q.get("evaluation", {}).get("overall_score", 75) for q in questions_asked]

    avg_own = sum(ownership_scores) // max(1, len(ownership_scores))
    avg_star = sum(star_scores) // max(1, len(star_scores))
    avg_spec = sum(spec_scores) // max(1, len(spec_scores))
    avg_total = sum(overall_scores) // max(1, len(overall_scores))

    questions_summary = "\n\n".join(
        f"Question #{idx+1} ({q.get('track', 'General')}): {q.get('text', '')}\n"
        f"Candidate Answer: {q.get('answer', '')}\n"
        f"Score: {q.get('evaluation', {}).get('overall_score', 75)}/100 | Ownership: {q.get('evaluation', {}).get('personal_ownership_score', 75)}/100\n"
        f"Feedback: {q.get('evaluation', {}).get('coaching_feedback', '')}"
        for idx, q in enumerate(questions_asked)
    )

    try:
        chain = _hr_report_prompt | _get_llm() | _hr_report_parser
        result = await chain.ainvoke(
            {
                "role": role,
                "company": company or "General Organization",
                "questions_summary": questions_summary,
                "format_instructions": _hr_report_parser.get_format_instructions(),
            }
        )

        strengths = result.get("strengths") or default_fallback["strengths"]
        weaknesses = result.get("weaknesses") or default_fallback["weaknesses"]
        summary = result.get("executive_summary") or default_fallback["executive_summary"]

        return {
            "total_score": int(result.get("total_score") or avg_total),
            "avg_ownership_score": int(result.get("avg_ownership_score") or avg_own),
            "avg_star_completeness": int(result.get("avg_star_completeness") or avg_star),
            "avg_specificity_score": int(result.get("avg_specificity_score") or avg_spec),
            "strengths": strengths if isinstance(strengths, list) else default_fallback["strengths"],
            "weaknesses": weaknesses if isinstance(weaknesses, list) else default_fallback["weaknesses"],
            "executive_summary": str(summary),
            "report_basis": "model" if summary is not default_fallback["executive_summary"] else "empirical",
            "report_error": None,
            "answers_not_model_scored": not_model_scored,
        }
    except Exception as exc:
        logger.warning("HR report generation error: %s. Using empirical fallback.", exc, exc_info=True)
        default_fallback["total_score"] = avg_total
        default_fallback["avg_ownership_score"] = avg_own
        default_fallback["avg_star_completeness"] = avg_star
        default_fallback["avg_specificity_score"] = avg_spec
        default_fallback["report_basis"] = "empirical"
        default_fallback["report_error"] = f"{type(exc).__name__}: {exc}"[:300]
        default_fallback["answers_not_model_scored"] = not_model_scored
        return default_fallback
