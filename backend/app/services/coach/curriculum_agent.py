"""Autonomous Curriculum Coach Agent implemented with LangGraph.

Analyzes cross-round historical telemetry from progress.py, identifies candidate
bottlenecks across JAM, Technical, Guesstimate, and HR rounds, and autonomously
synthesizes a personalized 7-Day Interview Roadmap with executable drill routes.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import SessionLocal
from app.models.guesstimate import GuesstimateCase
from app.models.hr import HRInterview
from app.models.session import Session as SessionModel, SessionAnalysis
from app.models.technical import TechnicalInterview
from app.services.technical.evaluator import _get_llm

logger = logging.getLogger("speakflow.coach.agent")


# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------
class CurriculumState(TypedDict):
    """LangGraph state representing the curriculum synthesis lifecycle."""

    user_id: int
    target_role: str
    history_summary: Dict[str, Any]
    identified_bottlenecks: List[Dict[str, Any]]
    curriculum_plan: Dict[str, Any]
    validation_passed: bool
    validation_errors: List[str]
    iteration_count: int


# ---------------------------------------------------------------------------
# Helper: Extract historical telemetry across all 4 rounds
# ---------------------------------------------------------------------------
def extract_candidate_history(user_id: int, db: Session) -> Dict[str, Any]:
    """Extract and aggregate cross-round metrics from database sessions."""
    user_filter = (
        (SessionModel.user_id == user_id)
        if user_id > 1
        else ((SessionModel.user_id == 1) | (SessionModel.user_id.is_(None)))
    )

    all_sessions = (
        db.scalars(
            select(SessionModel)
            .where(user_filter)
            .order_by(SessionModel.created_at.asc())
        )
        .all()
    )

    jam_sessions = [
        s for s in all_sessions if s.round_type in ("jam", "general", None)
    ]
    tech_sessions = [s for s in all_sessions if s.round_type == "technical"]
    guess_sessions = [s for s in all_sessions if s.round_type == "guesstimate"]
    hr_sessions = [s for s in all_sessions if s.round_type == "hr"]

    # 1. JAM Telemetry
    jam_analyses = [s.analysis for s in jam_sessions if s.analysis]
    jam_summary = {
        "attempt_count": len(jam_sessions),
        "completed_count": len(jam_analyses),
        "avg_clarity": (
            round(sum(a.clarity_score for a in jam_analyses) / len(jam_analyses), 1)
            if jam_analyses
            else 0.0
        ),
        "avg_pace": (
            round(sum(a.speaking_pace for a in jam_analyses) / len(jam_analyses), 1)
            if jam_analyses
            else 0.0
        ),
        "avg_filler_words": (
            round(
                sum(a.filler_words_count for a in jam_analyses) / len(jam_analyses), 1
            )
            if jam_analyses
            else 0.0
        ),
        "avg_eye_contact": (
            round(
                sum(a.eye_contact_percentage for a in jam_analyses)
                / len(jam_analyses),
                1,
            )
            if jam_analyses
            else 0.0
        ),
        "latest_score": (
            round(jam_analyses[-1].clarity_score, 1) if jam_analyses else None
        ),
    }

    # 2. Technical Telemetry
    tech_scores = [
        float(s.overall_score)
        for s in tech_sessions
        if s.overall_score is not None
    ]
    conciseness_scores: List[float] = []
    rambling_flags: List[bool] = []
    understanding_scores: List[float] = []

    for s in tech_sessions:
        tech_detail = s.technical_detail
        if tech_detail and isinstance(tech_detail.questions, list):
            for q in tech_detail.questions:
                if isinstance(q, dict):
                    if q.get("conciseness_score") is not None:
                        conciseness_scores.append(float(q["conciseness_score"]) * 10.0)
                    if q.get("rambling_detected") is not None:
                        rambling_flags.append(bool(q["rambling_detected"]))
                    if q.get("applied_understanding_score") is not None:
                        understanding_scores.append(
                            float(q["applied_understanding_score"]) * 10.0
                        )

    tech_summary = {
        "attempt_count": len(tech_sessions),
        "completed_count": len(tech_scores),
        "avg_score": (
            round(sum(tech_scores) / len(tech_scores), 1) if tech_scores else 0.0
        ),
        "latest_score": tech_scores[-1] if tech_scores else None,
        "avg_conciseness": (
            round(sum(conciseness_scores) / len(conciseness_scores), 1)
            if conciseness_scores
            else None
        ),
        "rambling_rate_percent": (
            round((sum(1 for f in rambling_flags if f) / len(rambling_flags)) * 100.0, 1)
            if rambling_flags
            else 0.0
        ),
        "avg_understanding": (
            round(sum(understanding_scores) / len(understanding_scores), 1)
            if understanding_scores
            else None
        ),
    }

    # 3. Guesstimate Telemetry
    guess_scores: List[float] = []
    mece_scores: List[float] = []
    math_scores: List[float] = []
    proxy_scores: List[float] = []
    sanity_scores: List[float] = []

    for s in guess_sessions:
        score = s.overall_score
        gc = s.guesstimate_detail
        ev = gc.evaluation if (gc and isinstance(gc.evaluation, dict)) else {}
        if score is None and ev:
            score = ev.get("overall_score")
        if score is not None:
            guess_scores.append(float(score))
        if ev:
            if ev.get("mece_score") is not None:
                mece_scores.append(float(ev["mece_score"]))
            if ev.get("mental_math_score") is not None:
                math_scores.append(float(ev["mental_math_score"]))
            if ev.get("assumption_score") is not None:
                proxy_scores.append(float(ev["assumption_score"]))
            if ev.get("sanity_check_score") is not None:
                sanity_scores.append(float(ev["sanity_check_score"]))

    guess_summary = {
        "attempt_count": len(guess_sessions),
        "completed_count": len(guess_scores),
        "avg_score": (
            round(sum(guess_scores) / len(guess_scores), 1) if guess_scores else 0.0
        ),
        "latest_score": guess_scores[-1] if guess_scores else None,
        "avg_mece": (
            round(sum(mece_scores) / len(mece_scores), 1) if mece_scores else None
        ),
        "avg_mental_math": (
            round(sum(math_scores) / len(math_scores), 1) if math_scores else None
        ),
        "avg_assumptions": (
            round(sum(proxy_scores) / len(proxy_scores), 1) if proxy_scores else None
        ),
        "avg_sanity_check": (
            round(sum(sanity_scores) / len(sanity_scores), 1) if sanity_scores else None
        ),
    }

    # 4. HR Telemetry
    hr_scores: List[float] = []
    star_completeness: List[float] = []
    ownership_scores: List[float] = []

    for s in hr_sessions:
        score = s.overall_score
        rep = s.report if isinstance(s.report, dict) else {}
        if score is None and rep:
            score = rep.get("total_score")
        if score is not None:
            hr_scores.append(float(score))
        if rep.get("avg_star_completeness") is not None:
            star_completeness.append(float(rep["avg_star_completeness"]))
        if rep.get("avg_ownership_score") is not None:
            ownership_scores.append(float(rep["avg_ownership_score"]))

    hr_summary = {
        "attempt_count": len(hr_sessions),
        "completed_count": len(hr_scores),
        "avg_score": (
            round(sum(hr_scores) / len(hr_scores), 1) if hr_scores else 0.0
        ),
        "latest_score": hr_scores[-1] if hr_scores else None,
        "avg_star_completeness": (
            round(sum(star_completeness) / len(star_completeness), 1)
            if star_completeness
            else None
        ),
        "avg_ownership": (
            round(sum(ownership_scores) / len(ownership_scores), 1)
            if ownership_scores
            else None
        ),
    }

    return {
        "jam": jam_summary,
        "technical": tech_summary,
        "guesstimate": guess_summary,
        "hr": hr_summary,
        "total_sessions": len(all_sessions),
    }


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------
async def audit_history_node(state: CurriculumState) -> Dict[str, Any]:
    """Node 1: Extract and aggregate cross-round telemetry from database sessions."""
    logger.info("LangGraph Node: audit_history for user %s", state.get("user_id"))
    history = state.get("history_summary")
    if not history or not history.get("jam"):
        with SessionLocal() as db:
            history = extract_candidate_history(state.get("user_id", 1), db)
    return {"history_summary": history}


def diagnose_bottlenecks_node(state: CurriculumState) -> Dict[str, Any]:
    """Node 2: Deterministic bottleneck evaluation detecting gaps across the 4 rounds."""
    logger.info("LangGraph Node: diagnose_bottlenecks")
    history = state.get("history_summary", {})
    bottlenecks: List[Dict[str, Any]] = []

    # 1. Guesstimate Rubrics
    g_data = history.get("guesstimate", {})
    if g_data.get("completed_count", 0) == 0:
        bottlenecks.append({
            "dimension": "Consulting Sizing Baseline",
            "round": "guesstimate",
            "severity": "high",
            "reason": "Zero guesstimate drills completed. Market sizing baseline is uncalibrated.",
            "target_metric": "Complete 1 market sizing case with MECE decomposition",
        })
    else:
        if g_data.get("avg_mental_math") is not None and g_data["avg_mental_math"] < 75.0:
            bottlenecks.append({
                "dimension": "Mental Math & Multi-Driver Sensitivity",
                "round": "guesstimate",
                "severity": "high",
                "reason": f"Mental math score ({g_data['avg_mental_math']}) is below competitive benchmark (75.0).",
                "target_metric": "Mental math >= 80, zero unit order-of-magnitude mismatches",
            })
        if g_data.get("avg_mece") is not None and g_data["avg_mece"] < 75.0:
            bottlenecks.append({
                "dimension": "MECE Tree Structuring",
                "round": "guesstimate",
                "severity": "high",
                "reason": f"MECE branch score ({g_data['avg_mece']}) indicates overlapping or missing segments.",
                "target_metric": "MECE structure score >= 85, clean 3-level tree partition",
            })
        if g_data.get("avg_sanity_check") is not None and g_data["avg_sanity_check"] < 70.0:
            bottlenecks.append({
                "dimension": "Sanity Check Benchmark Calibration",
                "round": "guesstimate",
                "severity": "medium",
                "reason": f"Sanity check score ({g_data['avg_sanity_check']}) suggests insufficient gut-check against reality.",
                "target_metric": "Explicit reality gut-check with population or competitor anchor",
            })

    # 2. Technical Rubrics
    t_data = history.get("technical", {})
    if t_data.get("completed_count", 0) == 0:
        bottlenecks.append({
            "dimension": "Technical System Architecture Baseline",
            "round": "technical",
            "severity": "high",
            "reason": "Zero technical interviews completed. Architectural communication needs baseline.",
            "target_metric": "Complete 1 full technical interview across system tradeoffs",
        })
    else:
        if t_data.get("rambling_rate_percent", 0) > 20.0:
            bottlenecks.append({
                "dimension": "Technical Conciseness & Anti-Rambling",
                "round": "technical",
                "severity": "high",
                "reason": f"Rambling detected in {t_data['rambling_rate_percent']}% of responses. Needs pyramid structure.",
                "target_metric": "Rambling rate < 10%, answer first with executive summary",
            })
        if t_data.get("avg_understanding") is not None and t_data["avg_understanding"] < 75.0:
            bottlenecks.append({
                "dimension": "System Trade-off Reasoning vs Rote Jargon",
                "round": "technical",
                "severity": "medium",
                "reason": f"Applied understanding ({t_data['avg_understanding']}) shows textbook definitions over trade-offs.",
                "target_metric": "Applied trade-off score >= 80, justify architectural compromises",
            })

    # 3. JAM Delivery & Prosody
    j_data = history.get("jam", {})
    if j_data.get("completed_count", 0) == 0:
        bottlenecks.append({
            "dimension": "Verbal Delivery & Presence Baseline",
            "round": "jam",
            "severity": "medium",
            "reason": "Zero JAM sessions recorded. Pacing, filler words, and eye contact uncalibrated.",
            "target_metric": "Complete 1 JAM speech session with video and audio tracking",
        })
    else:
        if j_data.get("avg_filler_words", 0) > 3.0:
            bottlenecks.append({
                "dimension": "Filler Word Eradication & Vocal Pauses",
                "round": "jam",
                "severity": "high",
                "reason": f"Averaging {j_data['avg_filler_words']} filler words per session. Pauses are filled with vocal crutches.",
                "target_metric": "Zero filler words, deliberate 1-2s tactical silence",
            })
        if j_data.get("avg_pace", 145) < 120 or j_data.get("avg_pace", 145) > 165:
            bottlenecks.append({
                "dimension": "Speaking Pace Modulation",
                "round": "jam",
                "severity": "medium",
                "reason": f"Speaking pace ({j_data['avg_pace']} WPM) is outside the executive sweet spot (135-155 WPM).",
                "target_metric": "Steady cadence between 135 and 155 WPM",
            })

    # 4. HR Leadership
    h_data = history.get("hr", {})
    if h_data.get("completed_count", 0) == 0:
        bottlenecks.append({
            "dimension": "Behavioral STAR & Ownership Baseline",
            "round": "hr",
            "severity": "medium",
            "reason": "Zero HR drills completed. STAR quantification and leadership agency need calibration.",
            "target_metric": "Complete 1 HR interview drill with Situation-Task-Action-Result structure",
        })
    else:
        if h_data.get("avg_star_completeness") is not None and h_data["avg_star_completeness"] < 75.0:
            bottlenecks.append({
                "dimension": "STAR Quantification & Measurable Results",
                "round": "hr",
                "severity": "high",
                "reason": f"STAR completeness ({h_data['avg_star_completeness']}) shows weak quantifiable metrics in Result component.",
                "target_metric": "STAR score >= 80 with explicit dollar, percentage, or latency impact",
            })
        if h_data.get("avg_ownership") is not None and h_data["avg_ownership"] < 75.0:
            bottlenecks.append({
                "dimension": "Personal Ownership ('I' vs 'We')",
                "round": "hr",
                "severity": "medium",
                "reason": f"Ownership score ({h_data['avg_ownership']}) indicates passive voice or diffusion of team responsibility.",
                "target_metric": "Ownership score >= 85, articulate exact individual actions taken",
            })

    # If candidate is balanced across all rounds, add mastery challenges
    if not bottlenecks:
        bottlenecks.append({
            "dimension": "High-Pressure Synthesis & Executive Mastery",
            "round": "technical",
            "severity": "low",
            "reason": "All round metrics meet or exceed standard placement thresholds. Ready for elite calibration.",
            "target_metric": "Maintain >= 85 cross-round composite score under tight time constraints",
        })

    # Sort bottlenecks: high severity first, then medium, then low
    severity_order = {"high": 0, "medium": 1, "low": 2}
    bottlenecks.sort(key=lambda b: severity_order.get(b["severity"], 3))

    return {"identified_bottlenecks": bottlenecks}


def _build_deterministic_fallback_roadmap(
    role: str, bottlenecks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Reliable pedagogical fallback that maps directly to diagnosed bottlenecks."""
    top_gap = (
        bottlenecks[0]
        if bottlenecks
        else {
            "dimension": "Holistic Synthesis",
            "round": "technical",
            "reason": "Calibrate end-to-end technical problem solving.",
            "target_metric": "Overall score >= 80",
        }
    )
    sec_gap = (
        bottlenecks[1]
        if len(bottlenecks) > 1
        else {
            "dimension": "Delivery Fluency",
            "round": "jam",
            "reason": "Strengthen cadence and eliminate filler pauses.",
            "target_metric": "Clarity score >= 80, pace 135-155 WPM",
        }
    )

    days = [
        {
            "day_number": 1,
            "title": f"Day 1: Remediation Drill — {top_gap['dimension']}",
            "round_type": top_gap.get("round", "guesstimate"),
            "drill_route": f"/{top_gap.get('round', 'guesstimate') if top_gap.get('round') != 'jam' else 'record'}",
            "drill_params": {"category": "Targeted Remediation", "difficulty": "Intermediate"},
            "focus_dimension": top_gap["dimension"],
            "pedagogical_rationale": f"Targets your highest priority placement gap: {top_gap.get('reason', 'Target core competency.')}",
            "target_metric_goal": top_gap.get("target_metric", "Score >= 80"),
            "status": "in_progress",
            "completed_at": None,
            "score_achieved": None,
        },
        {
            "day_number": 2,
            "title": f"Day 2: Core Strengthening — {sec_gap['dimension']}",
            "round_type": sec_gap.get("round", "jam"),
            "drill_route": f"/{sec_gap.get('round', 'jam') if sec_gap.get('round') != 'jam' else 'record'}",
            "drill_params": {"category": "Foundation Strengthening", "difficulty": "Intermediate"},
            "focus_dimension": sec_gap["dimension"],
            "pedagogical_rationale": f"Resolves secondary bottleneck: {sec_gap.get('reason', 'Strengthen foundation.')}",
            "target_metric_goal": sec_gap.get("target_metric", "Score >= 75"),
            "status": "pending",
            "completed_at": None,
            "score_achieved": None,
        },
        {
            "day_number": 3,
            "title": "Day 3: Guesstimate Market Sizing & Tornado Driver Defense",
            "round_type": "guesstimate",
            "drill_route": "/guesstimate",
            "drill_params": {"category": "Tech & SaaS", "difficulty": "Hard"},
            "focus_dimension": "MECE Tree Partition & Math Accuracy",
            "pedagogical_rationale": "Forces strict top-down segmentation and validates high-volatility assumption drivers.",
            "target_metric_goal": "Overall score >= 80, candidate estimate within plausible industry range",
            "status": "pending",
            "completed_at": None,
            "score_achieved": None,
        },
        {
            "day_number": 4,
            "title": "Day 4: JAM Executive Presence & Cadence Control",
            "round_type": "jam",
            "drill_route": "/record",
            "drill_params": {"mode": "executive_prompt", "target_pace": "145 WPM"},
            "focus_dimension": "Pacing Stability & Zero Filler Words",
            "pedagogical_rationale": "Calibrates speech prosody, ensuring smooth 135-155 WPM delivery without hesitation.",
            "target_metric_goal": "Pace between 135-155 WPM, filler word count <= 2",
            "status": "pending",
            "completed_at": None,
            "score_achieved": None,
        },
        {
            "day_number": 5,
            "title": "Day 5: Deep Technical Architecture & Trade-Off Defense",
            "round_type": "technical",
            "drill_route": "/technical",
            "drill_params": {"role": role, "tier": "tier1_product", "max_questions": 4},
            "focus_dimension": "System Trade-off Articulation & Conciseness",
            "pedagogical_rationale": "Eliminates rambling; teaches top-line architectural justification before diving into code.",
            "target_metric_goal": "Technical score >= 85, rambling detected in 0 questions",
            "status": "pending",
            "completed_at": None,
            "score_achieved": None,
        },
        {
            "day_number": 6,
            "title": "Day 6: Behavioral Leadership & STAR Impact Quantification",
            "round_type": "hr",
            "drill_route": "/hr",
            "drill_params": {"mode": "leadership_ownership", "track": "conflict_resolution"},
            "focus_dimension": "Measurable Result Metrics & 'I' Personal Agency",
            "pedagogical_rationale": "Refines behavioral interview storytelling using verifiable metrics and individual ownership.",
            "target_metric_goal": "STAR completeness >= 85, ownership score >= 80",
            "status": "pending",
            "completed_at": None,
            "score_achieved": None,
        },
        {
            "day_number": 7,
            "title": f"Day 7: Full Mock Placement Simulation ({role})",
            "round_type": "technical",
            "drill_route": "/technical",
            "drill_params": {"role": role, "tier": "tier1_product", "mock_simulation": True},
            "focus_dimension": "Comprehensive Cross-Round Synthesis",
            "pedagogical_rationale": "End-to-end simulation consolidating communication, analytical structure, and technical depth.",
            "target_metric_goal": "Combined readiness verdict: 'Strong Hire' / 'Tier-1 Ready'",
            "status": "pending",
            "completed_at": None,
            "score_achieved": None,
        },
    ]

    return {
        "roadmap_title": f"7-Day Placement Acceleration Roadmap: {role}",
        "target_role": role,
        "focus_areas": [b["dimension"] for b in bottlenecks[:3]],
        "days": days,
    }


async def synthesize_roadmap_node(state: CurriculumState) -> Dict[str, Any]:
    """Node 3: LLM generates an adaptive 7-day personalized syllabus."""
    logger.info("LangGraph Node: synthesize_roadmap (iteration=%s)", state.get("iteration_count", 0))
    role = state.get("target_role", "General Placement")
    bottlenecks = state.get("identified_bottlenecks", [])
    history = state.get("history_summary", {})

    prompt = f"""You are the SpeakFlow Autonomous Curriculum Coach Agent.
Analyze the candidate's historical interview metrics and synthesized placement bottlenecks to generate a 7-day personalized interview preparation curriculum.

CANDIDATE TARGET ROLE: {role}

DIAGNOSED BOTTLENECKS (Sorted by urgency):
{json.dumps(bottlenecks, indent=2)}

HISTORICAL PERFORMANCE OVERVIEW:
- JAM: {json.dumps(history.get('jam', {}))}
- Technical: {json.dumps(history.get('technical', {}))}
- Guesstimate: {json.dumps(history.get('guesstimate', {}))}
- HR Behavioral: {json.dumps(history.get('hr', {}))}

REQUIREMENTS:
1. Generate exactly 7 chronological days (Day 1 through Day 7).
2. For each day, provide:
   - day_number: 1..7 (integer)
   - title: concise, high-impact title
   - round_type: exactly one of ["jam", "technical", "guesstimate", "hr"]
   - drill_route: exactly one of ["/record", "/technical", "/guesstimate", "/hr"] (Note: JAM uses /record)
   - drill_params: JSON dict with parameters like category, difficulty, or role
   - focus_dimension: the exact skill/rubric targeted
   - pedagogical_rationale: 1-2 sentences explaining why this drill is prescribed based on their bottlenecks
   - target_metric_goal: concrete quantitative threshold (e.g. "Mental math >= 80")
   - status: "in_progress" for Day 1, "pending" for Days 2-7
3. Ensure the top 2 bottlenecks are directly addressed in Days 1 and 2.
4. Day 7 should be a capstone mock simulation for {role}.

Return ONLY valid JSON matching this schema:
{{
  "roadmap_title": "7-Day Placement Acceleration Roadmap: ...",
  "target_role": "{role}",
  "focus_areas": ["Bottleneck 1", "Bottleneck 2", "Bottleneck 3"],
  "days": [
    {{
      "day_number": 1,
      "title": "...",
      "round_type": "guesstimate",
      "drill_route": "/guesstimate",
      "drill_params": {{}},
      "focus_dimension": "...",
      "pedagogical_rationale": "...",
      "target_metric_goal": "...",
      "status": "in_progress",
      "completed_at": null,
      "score_achieved": null
    }}
  ]
}}"""

    plan = None
    plan = None
    try:
        import asyncio
        import re

        llm = _get_llm()
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=25.0)
        text_content = response.content if hasattr(response, "content") else str(response)

        # Robust JSON extraction
        clean_json = text_content.strip()
        match = re.search(r"(\{.*\})", clean_json, re.DOTALL)
        if match:
            candidate_str = match.group(1)
            parsed = json.loads(candidate_str)
            if isinstance(parsed, dict) and "days" in parsed and len(parsed["days"]) == 7:
                plan = parsed
    except Exception as exc:
        logger.warning("LLM curriculum synthesis fell back to deterministic generator: %s", exc)

    if not plan:
        plan = _build_deterministic_fallback_roadmap(role, bottlenecks)

    return {
        "curriculum_plan": plan,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


def validate_feasibility_node(state: CurriculumState) -> Dict[str, Any]:
    """Node 4: Deterministic guardrail verifying drill routes, day counts, and schema."""
    logger.info("LangGraph Node: validate_feasibility")
    plan = state.get("curriculum_plan", {})
    days = plan.get("days", [])
    errors: List[str] = []

    valid_routes = {"/record", "/technical", "/guesstimate", "/hr"}
    valid_rounds = {"jam", "technical", "guesstimate", "hr"}

    if len(days) != 7:
        errors.append(f"Expected 7 days in curriculum, got {len(days)}")

    for i, d in enumerate(days, 1):
        if d.get("drill_route") not in valid_routes:
            # Fix route automatically if mapping is close
            if d.get("round_type") == "jam":
                d["drill_route"] = "/record"
            elif d.get("round_type") in valid_rounds:
                d["drill_route"] = f"/{d['round_type']}"
            else:
                errors.append(f"Day {i} has invalid drill_route '{d.get('drill_route')}'")
        if d.get("round_type") not in valid_rounds:
            d["round_type"] = "technical"

    passed = len(errors) == 0
    return {
        "validation_passed": passed,
        "validation_errors": errors,
        "curriculum_plan": plan,
    }


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------
def route_validation(
    state: CurriculumState,
) -> Literal["synthesize_roadmap", "finalize"]:
    """Conditional edge: retry if validation fails and iteration limit not exceeded."""
    if not state.get("validation_passed") and state.get("iteration_count", 0) < 2:
        logger.warning(
            "Curriculum validation failed (%s). Looping back to synthesize_roadmap.",
            state.get("validation_errors"),
        )
        return "synthesize_roadmap"
    return "finalize"


# ---------------------------------------------------------------------------
# State Graph Construction
# ---------------------------------------------------------------------------
def _build_curriculum_graph():
    builder = StateGraph(CurriculumState)

    builder.add_node("audit_history", audit_history_node)
    builder.add_node("diagnose_bottlenecks", diagnose_bottlenecks_node)
    builder.add_node("synthesize_roadmap", synthesize_roadmap_node)
    builder.add_node("validate_feasibility", validate_feasibility_node)

    builder.add_edge(START, "audit_history")
    builder.add_edge("audit_history", "diagnose_bottlenecks")
    builder.add_edge("diagnose_bottlenecks", "synthesize_roadmap")
    builder.add_edge("synthesize_roadmap", "validate_feasibility")

    builder.add_conditional_edges(
        "validate_feasibility",
        route_validation,
        {
            "synthesize_roadmap": "synthesize_roadmap",
            "finalize": END,
        },
    )

    return builder.compile()


curriculum_graph = _build_curriculum_graph()


# ---------------------------------------------------------------------------
# Public Execution API
# ---------------------------------------------------------------------------
async def generate_curriculum_plan(
    user_id: int = 1,
    target_role: str = "General Placement",
    history_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute the LangGraph state machine to generate a personalized 7-day roadmap."""
    initial_state: CurriculumState = {
        "user_id": user_id,
        "target_role": target_role,
        "history_summary": history_summary or {},
        "identified_bottlenecks": [],
        "curriculum_plan": {},
        "validation_passed": False,
        "validation_errors": [],
        "iteration_count": 0,
    }

    final_state = await curriculum_graph.ainvoke(initial_state)
    return {
        "bottlenecks": final_state.get("identified_bottlenecks", []),
        "plan": final_state.get("curriculum_plan", {}),
        "history_summary": final_state.get("history_summary", {}),
    }
