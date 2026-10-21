"""Technical interview evaluator using OpenRouter Nemotron with local Ollama fallback."""
import logging
from typing import Optional

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

    # Dynamically re-read .env if key is updated
    env_vals = dotenv_values(str(settings.upload_dir.parent / ".env"))
    current_key = env_vals.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key

    if _llm is None or _cached_key != current_key:
        _cached_key = current_key
        if current_key and current_key.startswith("sk-"):
            logger.info("Using OpenRouter LLM: %s", settings.chat_model)
            _llm = ChatOpenAI(
                model=settings.chat_model,
                api_key=current_key,
                base_url=settings.openrouter_base_url,
                max_tokens=2048,
                temperature=0.7,
            )
        else:
            logger.info("OpenRouter key not found. Using local Ollama fallback: %s at %s", settings.ollama_model, settings.ollama_base_url)
            from langchain_community.chat_models import ChatOllama
            _llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                temperature=0.7,
            )
    return _llm


# ---------------------------------------------------------
# Schemas for LangChain Output Parsers
# ---------------------------------------------------------
class QuestionSchema(BaseModel):
    id: str = Field(default="q1", description="Identifier for the question, e.g., q1")
    text: str = Field(description="The interview question text")
    type: str = Field(
        default="behavioral",
        description="Type of question: behavioral, conceptual, or situational",
    )


class StarBreakdownSchema(BaseModel):
    situation: bool = Field(default=True, description="Did candidate set context/situation?")
    task: bool = Field(default=True, description="Did candidate define the objective/task?")
    action: bool = Field(default=True, description="Did candidate describe their specific implementation action?")
    result: bool = Field(default=True, description="Did candidate quantify or state concrete outcome/impact?")
    structure_feedback: str = Field(
        default="Good structure.",
        description="Coaching tip on STAR structure completeness",
    )


class EvaluationSchema(BaseModel):
    score: int = Field(
        default=7,
        description="Integer score between 1 and 10 evaluating the candidate's answer",
    )
    feedback: str = Field(
        default="Good response.",
        description="Constructive and actionable feedback explaining the score",
    )
    # 1. Technical Conciseness & Rambling Penalty
    conciseness_score: int = Field(
        default=8,
        description="Score between 1 and 10 for verbal conciseness and high signal-to-noise ratio",
    )
    rambling_detected: bool = Field(
        default=False,
        description="True if candidate rambled, looped circularly, or padded response unnecessarily",
    )
    rambling_critique: str = Field(
        default="Direct and well-paced delivery.",
        description="Specific critique explaining if/where candidate rambled or repeated themselves",
    )
    # 2. Jargon vs. Understanding Detection
    jargon_vs_understanding: str = Field(
        default="applied_intuition",
        description="One of: 'textbook_rote' (memorized definitions), 'balanced', or 'applied_intuition' (practical understanding with real-world context)",
    )
    applied_understanding_score: int = Field(
        default=8,
        description="Score between 1 and 10 evaluating whether the candidate explained the concept with practical intuition rather than memorized textbook definitions",
    )
    jargon_critique: str = Field(
        default="Demonstrated practical intuition.",
        description="Evaluation of whether explanation relied on textbook definitions or genuine practical grasp",
    )
    # 3. STAR Structure Breakdown
    star_breakdown: StarBreakdownSchema = Field(
        default_factory=StarBreakdownSchema,
        description="Breakdown of Situation, Task, Action, and Result coverage",
    )
    ideal_concise_script: str = Field(
        default="",
        description="An exemplary, high-impact 45-60 second verbal articulation of how a top student candidate should answer this question",
    )


class ReportSchema(BaseModel):
    total_score: int = Field(
        default=75,
        description="Overall interview score from 0 to 100",
    )
    avg_conciseness_score: int = Field(
        default=75,
        description="Average communication conciseness score (0-100)",
    )
    avg_understanding_score: int = Field(
        default=80,
        description="Average conceptual vs textbook understanding score (0-100)",
    )
    rambling_rate_percent: int = Field(
        default=0,
        description="Percentage of questions where rambling was detected",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Key communication and technical strengths demonstrated during the interview",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Areas for student candidate improvement",
    )
    summary: str = Field(
        default="",
        description="Executive summary of the student candidate's verbal articulation and interview readiness",
    )


# ---------------------------------------------------------
# Prompts & LCEL Chains
# ---------------------------------------------------------
_question_parser = JsonOutputParser(pydantic_object=QuestionSchema)
_question_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert interviewer conducting a conversational mock interview for the position of {role}.\n\n"
            "INTERVIEW PHILOSOPHY:\n"
            "- Focus strictly on IN-CONTEXT COMMUNICATION, structured reasoning, conceptual explanation, and behavioral scenarios.\n"
            "- STRICT RULE: DO NOT ask the candidate to write code, provide syntax, or implement code blocks.\n"
            "- All questions must be conversational questions that test how effectively the candidate explains concepts, defends design choices, and navigates workplace scenarios.\n\n"
            "TARGET FOCUS FOR THIS ROUND:\n"
            "{target_focus}\n\n"
            "CRITICAL ANTI-REPETITION RULES:\n"
            "1. You MUST NOT repeat, rephrase, or overlap with any previously asked question listed below.\n"
            "2. Explore an entirely different scenario, concept, or real-world challenge from the candidate's background/role.\n"
            "3. Ask ONE clear, engaging, and thought-provoking question.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Role: {role}\n\n"
            "Resume / Job Context:\n{resume_context}\n\n"
            "PREVIOUSLY ASKED QUESTIONS (DO NOT REPEAT):\n{asked_questions}\n\n"
            "Generate Question #{question_num} matching the target communication focus.",
        ),
    ]
)

_evaluation_parser = JsonOutputParser(pydantic_object=EvaluationSchema)
_evaluation_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert technical interviewer and communication coach evaluating a student / campus placement candidate's verbal answer.\n"
            "This interview explicitly measures VERBAL ARTICULATION, CONCISENESS, and CONCEPTUAL INTUITION.\n\n"
            "EVALUATE STRICTLY ACCORDING TO THESE 3 COMMUNICATION CRITERIA:\n\n"
            "1. TECHNICAL CONCISENESS & 'RAMBLING' PENALTY (CRITICAL):\n"
            "- Did the candidate deliver a high Signal-to-Noise response (45-75 seconds equivalent)?\n"
            "- Did they talk in circular loops, repeat the same point 2+ times in different words, or pad with empty filler phrases ('basically what I mean to say is', 'you know') because they were afraid to end on silence?\n"
            "- If rambling or circular repetition is present, set rambling_detected=True, heavily penalize conciseness_score (1-6), and explicitly state in rambling_critique where they should have stopped.\n\n"
            "2. JARGON VS. UNDERSTANDING DETECTION (TEXTBOOK VS. INTUITION):\n"
            "- Did the candidate recite textbook definitions verbatim (e.g. GeeksforGeeks/Wikipedia definitions of OOP, ACID, or algorithms) without practical depth? That is 'textbook_rote'.\n"
            "- Or did they explain the concept with real-world intuition, everyday analogies, or practical applied scenarios? That is 'applied_intuition'.\n"
            "- Score applied_understanding_score (1-10) and detail in jargon_critique.\n\n"
            "3. STAR METHOD & STRUCTURE BREAKDOWN:\n"
            "- For project, situational, or behavioral answers, verify the 4 pillars: Situation, Task, Action (what THEY specifically did), Result (concrete outcome/impact).\n"
            "- Mark true/false for each in star_breakdown and provide actionable structure_feedback.\n\n"
            "4. IDEAL CONCISE SCRIPT:\n"
            "- Write an ideal 45-60 second verbal script (ideal_concise_script) demonstrating how a stellar candidate would concisely articulate this answer without jargon overload or rambling.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Question: {question_text}\n"
            "Question Type: {question_type}\n"
            "Candidate's Answer: {answer}\n\n"
            "Resume Context:\n{resume_context}",
        ),
    ]
)

_report_parser = JsonOutputParser(pydantic_object=ReportSchema)
_report_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert career coach evaluating a student candidate's technical interview communication report.\n"
            "Assess total score (0-100), average conciseness score (0-100), average applied understanding score (0-100), rambling rate (%), key communication strengths, constructive areas for improvement, and a student-tailored executive summary focusing on how clearly and concisely they articulate technical ideas.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Role: {role}\n\n"
            "Interview Session History:\n{questions_summary}\n\n"
            "Generate the final student-focused technical communication report.",
        ),
    ]
)

# 5 Communication-Centric Interview Stages
_STAGE_FOCUSES = [
    "1. Background & Architectural Articulation: Ask the candidate to explain the architecture of a major system they worked on and articulate the business and technical impact to stakeholders.",
    "2. Conceptual Explanation & Clarity: Ask the candidate to explain a complex technical mechanism or concept from their stack in simple, structured terms as if communicating to a teammate or junior engineer.",
    "3. Collaboration & Resolving Conflict: Ask a behavioral question about navigating technical disagreements with engineers, cross-functional partners, or product managers, and reaching consensus.",
    "4. Problem Solving & Incident Communication: Ask how they communicate and coordinate during a critical production failure or high-pressure outage (stakeholder updates, debugging thought process, post-mortems).",
    "5. Strategic Trade-offs & Engineering Philosophy: Ask how they evaluate and communicate difficult trade-offs (e.g. shipping velocity vs. technical debt, monolithic vs. microservices, build vs. buy).",
]

_DEFAULT_FALLBACKS = [
    {"text": "Can you walk me through the high-level architecture of a key project you built, and how you communicated its technical value to your team?", "type": "behavioral"},
    {"text": "How would you explain the concept of asynchronous processing and event loops to a junior developer or a non-technical stakeholder?", "type": "conceptual"},
    {"text": "Tell me about a time you had a strong technical disagreement with a teammate or product manager. How did you communicate your perspective and reach a resolution?", "type": "behavioral"},
    {"text": "Imagine a critical service suffers an unexpected outage during peak hours. How do you communicate with your team, manage stakeholder expectations, and run the post-mortem?", "type": "situational"},
    {"text": "When facing tight deadlines, how do you communicate the trade-offs between shipping quickly versus taking on technical debt, and how do you prioritize?", "type": "situational"},
]


async def generate_question(
    role: str, resume_context: str, questions_asked: list[dict]
) -> dict:
    """Generate a tailored interview question using LangChain LCEL."""
    asked_questions = "\n".join(
        f"- {q.get('text', '')}" for q in questions_asked
    ) or "None yet (this is the first question)."

    q_index = len(questions_asked)
    next_id = f"q{q_index + 1}"
    focus = _STAGE_FOCUSES[q_index % len(_STAGE_FOCUSES)]
    fallback_data = _DEFAULT_FALLBACKS[q_index % len(_DEFAULT_FALLBACKS)]

    default_fallback = {
        "id": next_id,
        "text": fallback_data["text"],
        "type": fallback_data["type"],
    }

    try:
        chain = _question_prompt | _get_llm() | _question_parser
        result = await chain.ainvoke(
            {
                "role": role,
                "target_focus": focus,
                "question_num": q_index + 1,
                "resume_context": resume_context or "No resume provided.",
                "asked_questions": asked_questions,
                "format_instructions": _question_parser.get_format_instructions(),
            }
        )
        return {
            "id": next_id,
            "text": str(result.get("text") or result.get("question") or default_fallback["text"]),
            "type": str(result.get("type") or default_fallback["type"]),
        }
    except Exception as exc:
        logger.warning("Dynamic question generation failed (%s). Using stage fallback.", exc)
        return default_fallback


async def evaluate_answer(
    question: dict, answer: str, resume_context: str
) -> dict:
    """Evaluate candidate answer using LangChain LCEL."""
    default_fallback = {
        "score": 6,
        "feedback": "Answer recorded. Continue to expand with specific examples and technical depth.",
    }

    try:
        chain = _evaluation_prompt | _get_llm() | _evaluation_parser
        result = await chain.ainvoke(
            {
                "question_text": question.get("text", "Interview question"),
                "question_type": question.get("type", "behavioral"),
                "answer": answer,
                "resume_context": resume_context or "General role context",
                "format_instructions": _evaluation_parser.get_format_instructions(),
            }
        )

        score = result.get("score")
        try:
            score = int(float(score))
        except (ValueError, TypeError):
            score = 7

        # Safely extract student communication metrics
        conciseness_score = result.get("conciseness_score")
        try:
            conciseness_score = int(float(conciseness_score))
        except (ValueError, TypeError):
            conciseness_score = 8

        applied_score = result.get("applied_understanding_score")
        try:
            applied_score = int(float(applied_score))
        except (ValueError, TypeError):
            applied_score = 8

        star = result.get("star_breakdown") or {}
        if not isinstance(star, dict):
            star = {
                "situation": True,
                "task": True,
                "action": True,
                "result": True,
                "structure_feedback": "Structure verified.",
            }

        return {
            "score": score if (1 <= score <= 10) else 7,
            "feedback": str(result.get("feedback") or default_fallback["feedback"]),
            "conciseness_score": max(1, min(10, conciseness_score)),
            "rambling_detected": bool(result.get("rambling_detected", False)),
            "rambling_critique": str(result.get("rambling_critique") or "Direct delivery without circular repetition."),
            "jargon_vs_understanding": str(result.get("jargon_vs_understanding") or "applied_intuition"),
            "applied_understanding_score": max(1, min(10, applied_score)),
            "jargon_critique": str(result.get("jargon_critique") or "Explained with practical intuition."),
            "star_breakdown": {
                "situation": bool(star.get("situation", True)),
                "task": bool(star.get("task", True)),
                "action": bool(star.get("action", True)),
                "result": bool(star.get("result", True)),
                "structure_feedback": str(star.get("structure_feedback") or "Good coverage of the STAR method."),
            },
            "ideal_concise_script": str(result.get("ideal_concise_script") or ""),
        }
    except Exception as exc:
        logger.warning("Answer evaluation failed (%s). Using fallback evaluation.", exc)
        return {
            **default_fallback,
            "conciseness_score": 7,
            "rambling_detected": False,
            "rambling_critique": "Crisp verbal articulation.",
            "jargon_vs_understanding": "applied_intuition",
            "applied_understanding_score": 7,
            "jargon_critique": "Solid conceptual understanding.",
            "star_breakdown": {
                "situation": True,
                "task": True,
                "action": True,
                "result": True,
                "structure_feedback": "Solid communication flow.",
            },
            "ideal_concise_script": "",
        }


async def generate_report(questions_asked: list[dict], role: str) -> dict:
    """Generate final interview scorecard and report using LangChain LCEL."""
    questions_summary = "\n".join(
        f"Q: {q.get('text', '')} | A: {q.get('answer', 'N/A')} | "
        f"Score: {q.get('score', 'N/A')} | Conciseness: {q.get('conciseness_score', 'N/A')}/10 | "
        f"Rambling: {'Yes' if q.get('rambling_detected') else 'No'} | "
        f"Understanding: {q.get('jargon_vs_understanding', 'applied')} | "
        f"Feedback: {q.get('feedback', 'N/A')}"
        for q in questions_asked
    ) or "No questions recorded."

    # Compute baseline metrics from per-question data if available
    total_q = max(1, len(questions_asked))
    calc_rambling_count = sum(1 for q in questions_asked if q.get("rambling_detected"))
    calc_rambling_rate = int((calc_rambling_count / total_q) * 100)
    calc_avg_conciseness = int(
        (sum(q.get("conciseness_score", 8) for q in questions_asked) / total_q) * 10
    )
    calc_avg_understanding = int(
        (sum(q.get("applied_understanding_score", 8) for q in questions_asked) / total_q) * 10
    )

    default_fallback = {
        "total_score": 75,
        "avg_conciseness_score": calc_avg_conciseness,
        "avg_understanding_score": calc_avg_understanding,
        "rambling_rate_percent": calc_rambling_rate,
        "strengths": ["Clear technical communication", "Direct explanations of core concepts"],
        "weaknesses": ["Could provide more concrete production examples and metrics"],
        "summary": "Completed the technical round with solid conceptual communication.",
    }

    try:
        chain = _report_prompt | _get_llm() | _report_parser
        result = await chain.ainvoke(
            {
                "role": role,
                "questions_summary": questions_summary,
                "format_instructions": _report_parser.get_format_instructions(),
            }
        )

        total_score = result.get("total_score")
        try:
            total_score = int(float(total_score))
        except (ValueError, TypeError):
            total_score = default_fallback["total_score"]

        avg_conciseness = result.get("avg_conciseness_score")
        try:
            avg_conciseness = int(float(avg_conciseness))
        except (ValueError, TypeError):
            avg_conciseness = calc_avg_conciseness

        avg_understanding = result.get("avg_understanding_score")
        try:
            avg_understanding = int(float(avg_understanding))
        except (ValueError, TypeError):
            avg_understanding = calc_avg_understanding

        rambling_rate = result.get("rambling_rate_percent")
        try:
            rambling_rate = int(float(rambling_rate))
        except (ValueError, TypeError):
            rambling_rate = calc_rambling_rate

        strengths = result.get("strengths") or default_fallback["strengths"]
        weaknesses = result.get("weaknesses") or default_fallback["weaknesses"]
        summary = result.get("summary") or default_fallback["summary"]

        return {
            "total_score": total_score,
            "avg_conciseness_score": max(0, min(100, avg_conciseness)),
            "avg_understanding_score": max(0, min(100, avg_understanding)),
            "rambling_rate_percent": max(0, min(100, rambling_rate)),
            "strengths": strengths if isinstance(strengths, list) else [str(strengths)],
            "weaknesses": weaknesses if isinstance(weaknesses, list) else [str(weaknesses)],
            "summary": str(summary),
        }
    except Exception as exc:
        logger.warning("Report generation failed (%s). Using fallback report.", exc)
        return default_fallback
