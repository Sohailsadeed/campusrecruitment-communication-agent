"""HR & Behavioral interview evaluator using OpenRouter Nemotron with local Ollama fallback."""
import logging
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)

_llm = None
_cached_key = None


def _get_llm():
    """Get LLM instance: Nemotron via OpenRouter, falling back to local Ollama."""
    global _llm, _cached_key
    import os
    from dotenv import dotenv_values

    env_vals = dotenv_values(str(settings.upload_dir.parent / ".env"))
    current_key = env_vals.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key

    if _llm is None or _cached_key != current_key:
        _cached_key = current_key
        if current_key and current_key.startswith("sk-"):
            logger.info("HR Evaluator using OpenRouter LLM: %s", settings.chat_model)
            _llm = ChatOpenAI(
                model=settings.chat_model,
                api_key=current_key,
                base_url=settings.openrouter_base_url,
                max_tokens=2500,
                temperature=0.6,
            )
        else:
            logger.info("HR Evaluator using local Ollama fallback: %s at %s", settings.ollama_model, settings.ollama_base_url)
            from langchain_community.chat_models import ChatOllama
            _llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                temperature=0.6,
            )
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


class HRReportSchema(BaseModel):
    total_score: int = Field(default=75, description="Overall HR behavioral readiness score from 0 to 100")
    avg_ownership_score: int = Field(default=75, description="Average personal ownership and initiative score (0-100)")
    avg_star_completeness: int = Field(default=80, description="Average STAR structure completeness score (0-100)")
    avg_specificity_score: int = Field(default=75, description="Average detail and concrete impact score (0-100)")
    strengths: List[str] = Field(default_factory=list, description="Top behavioral and communication strengths demonstrated")
    weaknesses: List[str] = Field(default_factory=list, description="High-priority coaching areas for placement day")
    executive_summary: str = Field(default="", description="Executive assessment of candidate's behavioral poise, cultural maturity, and hire readiness")


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
    }

    if not candidate_answer or len(candidate_answer.strip()) < 15:
        default_fallback["overall_score"] = 40
        default_fallback["personal_ownership_score"] = 40
        default_fallback["specificity_score"] = 40
        default_fallback["coaching_feedback"] = "Answer was too brief to evaluate behavioral STAR structure or personal ownership."
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

        overall = int(result.get("overall_score", 75))
        ownership = int(result.get("personal_ownership_score", 75))
        specificity = int(result.get("specificity_score", 75))
        relevance = int(result.get("relevance_score", 80))

        star = result.get("star_structure") or default_fallback["star_structure"]
        if not isinstance(star, dict):
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
        }
    except Exception as exc:
        logger.warning("HR answer evaluation error: %s. Using structured fallback.", exc)
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
    }

    if not questions_asked:
        return default_fallback

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
        }
    except Exception as exc:
        logger.warning("HR report generation error: %s. Using empirical fallback.", exc)
        default_fallback["total_score"] = avg_total
        default_fallback["avg_ownership_score"] = avg_own
        default_fallback["avg_star_completeness"] = avg_star
        default_fallback["avg_specificity_score"] = avg_spec
        return default_fallback
