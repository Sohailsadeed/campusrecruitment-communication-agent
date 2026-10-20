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


def _get_llm():
    """Get LLM instance: Nemotron via OpenRouter, falling back to local Ollama."""
    global _llm
    if _llm is None:
        if settings.openrouter_api_key and settings.openrouter_api_key.startswith("sk-"):
            logger.info("Using OpenRouter LLM: %s", settings.chat_model)
            _llm = ChatOpenAI(
                model=settings.chat_model,
                api_key=settings.openrouter_api_key,
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


class EvaluationSchema(BaseModel):
    score: int = Field(
        default=7,
        description="Integer score between 1 and 10 evaluating the candidate's answer",
    )
    feedback: str = Field(
        default="Good response.",
        description="Constructive and actionable feedback explaining the score",
    )


class ReportSchema(BaseModel):
    total_score: int = Field(
        default=75,
        description="Overall interview score from 0 to 100",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Key strengths demonstrated during the interview",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Areas for candidate improvement",
    )
    summary: str = Field(
        default="",
        description="Executive summary of the candidate's overall performance",
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
            "You are an expert interviewer evaluating a candidate's answer.\n"
            "Focus on how clearly, persuasively, and thoughtfully the candidate communicates their technical knowledge and experience.\n"
            "Score from 1 to 10 and provide concise, constructive feedback.\n\n"
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
            "You are an expert career coach and hiring manager. Generate a comprehensive final interview report.\n"
            "Assess total score (0-100), key communication strengths, constructive areas for improvement, and an executive summary.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Role: {role}\n\n"
            "Interview Session History:\n{questions_summary}\n\n"
            "Generate the final interview report.",
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

        return {
            "score": score if (1 <= score <= 10) else 7,
            "feedback": str(result.get("feedback") or default_fallback["feedback"]),
        }
    except Exception as exc:
        logger.warning("Answer evaluation failed (%s). Using fallback evaluation.", exc)
        return default_fallback


async def generate_report(questions_asked: list[dict], role: str) -> dict:
    """Generate final interview scorecard and report using LangChain LCEL."""
    questions_summary = "\n".join(
        f"Q: {q.get('text', '')} | A: {q.get('answer', 'N/A')} | "
        f"Score: {q.get('score', 'N/A')} | Feedback: {q.get('feedback', 'N/A')}"
        for q in questions_asked
    ) or "No questions recorded."

    default_fallback = {
        "total_score": 75,
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

        strengths = result.get("strengths") or default_fallback["strengths"]
        weaknesses = result.get("weaknesses") or default_fallback["weaknesses"]
        summary = result.get("summary") or default_fallback["summary"]

        return {
            "total_score": total_score,
            "strengths": strengths if isinstance(strengths, list) else [str(strengths)],
            "weaknesses": weaknesses if isinstance(weaknesses, list) else [str(weaknesses)],
            "summary": str(summary),
        }
    except Exception as exc:
        logger.warning("Report generation failed (%s). Using fallback report.", exc)
        return default_fallback
