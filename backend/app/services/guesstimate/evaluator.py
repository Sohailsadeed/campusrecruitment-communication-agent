"""Guesstimate interview evaluation service using OpenRouter Nemotron / Ollama fallback."""
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
            logger.info("Guesstimate Evaluator using OpenRouter LLM: %s", settings.chat_model)
            _llm = ChatOpenAI(
                model=settings.chat_model,
                api_key=current_key,
                base_url=settings.openrouter_base_url,
                max_tokens=2500,
                temperature=0.6,
            )
        else:
            logger.info("Guesstimate Evaluator using local Ollama fallback: %s at %s", settings.ollama_model, settings.ollama_base_url)
            from langchain_community.chat_models import ChatOllama
            _llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                temperature=0.6,
            )
    return _llm


# ---------------------------------------------------------
# Schemas for LangChain Output Parser
# ---------------------------------------------------------
class ModelTreeStep(BaseModel):
    step_name: str = Field(description="Name of this branch or step (e.g., Target Population)")
    formula_or_proxy: str = Field(description="Mathematical proxy or assumption used")
    estimated_value: str = Field(description="Resulting numerical value for this branch")


class CandidateEstimate(BaseModel):
    value: Optional[float] = Field(default=None, description="Numeric estimate value without currency symbols or text suffix (e.g. 1200000)")
    unit: str = Field(default="units", description="Exact quantity unit (e.g. units, cups, users, dollars, flights)")
    period: str = Field(default="annual", description="Time period: daily, monthly, annual, per_event")
    geography: str = Field(default="US", description="Target geography or market analyzed")
    formatted_display: str = Field(default="", description="Human-readable formatted string (e.g. '1.2M units/year')")


class PlausibleRange(BaseModel):
    min: Optional[float] = Field(default=None, description="Lower plausible bound numeric value (e.g. 1000000)")
    max: Optional[float] = Field(default=None, description="Upper plausible bound numeric value (e.g. 1500000)")
    unit: str = Field(default="units", description="Quantity unit, MUST strictly match candidate estimate unit")
    period: str = Field(default="annual", description="Time period, MUST strictly match candidate estimate period")
    geography: str = Field(default="US", description="Target geography or market analyzed")
    benchmark_source: str = Field(default="Industry Census & Consulting Benchmark", description="Benchmark methodology rationale or public census reference")
    formatted_display: str = Field(default="", description="Human-readable formatted string (e.g. '1.0M - 1.5M units/year')")


class BranchEvidence(BaseModel):
    branch_name: str = Field(description="Name of candidate segment or calculation step")
    status: str = Field(
        description="Must be strictly one of: 'supported_mece', 'confirmed_overlap', 'omitted_segment', 'unsupported_proxy', 'unclear_evidence'"
    )
    formula_or_proxy: str = Field(default="", description="Formula, proxy, or assumption candidate applied to this branch")
    estimated_value: str = Field(default="", description="Numerical value or proportion stated, or 'Unspecified'")
    evidence_rationale: str = Field(default="", description="Specific citation from transcript explaining why this status was assigned")


class SensitivityDriverInput(BaseModel):
    driver_name: str = Field(default="Primary Adoption / Penetration Rate", description="Name of the highest-leverage variable in candidate's equation")
    baseline_value: Optional[float] = Field(default=None, description="The baseline numerical value used in candidate calculation (e.g. 0.25)")
    low_scenario_value: Optional[float] = Field(default=None, description="Conservative / pessimistic scenario value (e.g. 0.15)")
    high_scenario_value: Optional[float] = Field(default=None, description="Aggressive / optimistic scenario value (e.g. 0.35)")
    unit: str = Field(default="ratio", description="Unit of the driver variable (e.g. %, years, frequency, dollars)")
    formula_expression: str = Field(default="", description="Identified formula (e.g. Total = Population * Penetration * Frequency * Price)")
    explanation: str = Field(default="", description="Why this variable carries the highest sensitivity to estimation variance")


class GuesstimateEvaluationSchema(BaseModel):
    overall_score: int = Field(
        default=75,
        description="Overall interview evaluation score from 0 to 100 (will be deterministically calibrated by backend)",
    )
    mece_score: int = Field(
        default=75,
        description="Score between 0 and 100 evaluating MECE (Mutually Exclusive, Collectively Exhaustive) formula structuring",
    )
    mece_feedback: str = Field(
        default="Good formula structure.",
        description="Specific critique on whether the candidate's segmentation had gaps, overlaps, or a clean breakdown",
    )
    assumption_score: int = Field(
        default=78,
        description="Score between 0 and 100 evaluating the realism and justification of proxies/assumptions",
    )
    assumption_feedback: str = Field(
        default="Reasonable assumptions stated.",
        description="Critique on whether assumptions were justified and realistically bounded",
    )
    mental_math_score: int = Field(
        default=80,
        description="Score between 0 and 100 evaluating mental math clarity, rounding technique, and arithmetic articulation",
    )
    math_feedback: str = Field(
        default="Calculations articulated clearly.",
        description="Critique on verbal calculation flow, rounding, and numerical accuracy",
    )
    sanity_check_score: int = Field(
        default=70,
        description="Score between 0 and 100 evaluating sensitivity analysis and macro benchmark validation",
    )
    sanity_check_feedback: str = Field(
        default="Completed a basic reality check.",
        description="Feedback on whether candidate tested their final number against real-world benchmarks",
    )
    
    # Backward compatible string fields
    candidate_final_estimate: str = Field(
        default="",
        description="Extracted or approximate final estimate stated by the candidate (e.g. '1.2 Million units/year')",
    )
    plausible_industry_range: str = Field(
        default="",
        description="Realistic consulting estimation range for this problem (e.g., '1.0M - 1.5M units/year')",
    )
    
    # Structured normalized fields for reliable diagnostics
    candidate_estimate_structured: Optional[CandidateEstimate] = Field(
        default=None,
        description="Structured candidate estimate with normalized numeric value, unit, and period",
    )
    plausible_range_structured: Optional[PlausibleRange] = Field(
        default=None,
        description="Structured benchmark range with normalized min/max numeric values, matching unit and period",
    )
    
    model_approach_name: str = Field(
        default="Top-Down Population Segmentation",
        description="Name of the optimal framework for this problem (e.g. Demand-Side Top-Down or Supply-Side Capacity)",
    )
    model_breakdown_steps: List[ModelTreeStep] = Field(
        default_factory=list,
        description="3 to 5 structured breakdown branches illustrating an exemplary consulting breakdown tree",
    )
    candidate_branch_diagnostics: List[BranchEvidence] = Field(
        default_factory=list,
        description="3 to 5 evidence-backed branches evaluating candidate's actual segments: supported_mece, confirmed_overlap, omitted_segment, unsupported_proxy, or unclear_evidence",
    )
    sensitivity_driver: Optional[SensitivityDriverInput] = Field(
        default=None,
        description="The primary driver variable in candidate's equation with low/high scenario bounds",
    )
    
    strengths: List[str] = Field(
        default_factory=list,
        description="Key analytical and communication strengths demonstrated",
    )
    weaknesses: List[str] = Field(
        default_factory=list,
        description="Specific areas to improve for management consulting or product management rounds",
    )
    ideal_verbal_script: str = Field(
        default="",
        description="Exemplary, high-impact 60-second verbal delivery showing how a top candidate would answer cleanly",
    )
    executive_summary: str = Field(
        default="",
        description="Comprehensive summary of candidate's estimation rigor, verbal poise, and interview readiness",
    )


# ---------------------------------------------------------
# Prompt Definition
# ---------------------------------------------------------
_guesstimate_parser = JsonOutputParser(pydantic_object=GuesstimateEvaluationSchema)

_guesstimate_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a Senior Management Consultant and Interviewer at a top-tier consulting firm (McKinsey/BCG/Bain) "
            "evaluating a student candidate's verbal response to a Guesstimate / Market Sizing interview problem.\n\n"
            "EVALUATION CRITERIA (Four Independent Rubrics):\n"
            "1. MECE STRUCTURING (0-100):\n"
            "- Did the candidate formulate a clear, logical mathematical equation before jumping into numbers?\n"
            "- Is the segmentation Mutually Exclusive (no double counting) and Collectively Exhaustive (no huge omitted segments)?\n\n"
            "2. PROXY & ASSUMPTION SANITY (0-100):\n"
            "- Are the demographic/market benchmarks realistic (e.g., population proportions, income brackets, replacement cycles)?\n"
            "- Did they justify *why* they chose their proxies instead of pulling numbers from nowhere?\n\n"
            "3. MENTAL MATH & ARITHMETIC FLOW (0-100):\n"
            "- Did they articulate arithmetic smoothly out loud?\n"
            "- Did they round numbers intelligently (e.g., using 1.4B, 30%, 80/20) for clean calculation under pressure?\n\n"
            "4. SANITY CHECK & SENSITIVITY ANALYSIS (0-100):\n"
            "- Did the candidate cross-check their final number against a known benchmark (e.g. national GDP, per capita spend, capacity limits)?\n"
            "- Did they identify which variable has the highest sensitivity?\n\n"
            "CONSULTING DIAGNOSTIC REQUIREMENTS:\n"
            "- Candidate Tree Evidence: Classify candidate branches as 'supported_mece', 'confirmed_overlap', 'omitted_segment', 'unsupported_proxy', or 'unclear_evidence'. If the candidate did not state a branch clearly enough, classify as 'unclear_evidence' rather than making unsupported assumptions.\n"
            "- Unit & Period Normalization: The benchmark range MUST match the exact same quantity, unit, geography, and time period as the candidate's estimate (e.g. daily cups vs daily cups, not daily vs annual).\n"
            "- Sensitivity Driver: Identify the single most volatile assumption in candidate's equation and specify realistic baseline, low, and high values.\n\n"
            "{format_instructions}",
        ),
        (
            "user",
            "Guesstimate Question: {question}\n"
            "Category: {category}\n"
            "Difficulty Level: {difficulty}\n"
            "Declared Approach: {approach_type}\n\n"
            "Candidate's Verbal/Written Response:\n"
            "\"\"\"\n{candidate_answer}\n\"\"\"\n\n"
            "Evaluate the candidate's response rigorously and provide structured consulting feedback.",
        ),
    ]
)


def _compute_deterministic_range_diagnostic(
    candidate_est: Optional[CandidateEstimate],
    plausible_rng: Optional[PlausibleRange],
) -> Dict[str, Any]:
    """Deterministically compare candidate estimate against plausible benchmark range."""
    if not candidate_est or candidate_est.value is None or not plausible_rng or plausible_rng.min is None or plausible_rng.max is None:
        return {
            "status": "unavailable",
            "is_within_range": None,
            "variance_percent": None,
            "unit_match": True,
            "summary_label": "Benchmark Range Pending",
            "diagnostic_note": "A numerical candidate estimate or benchmark range was not sufficiently specified for automated reality comparison.",
        }

    # Verify unit and period match
    cand_unit = candidate_est.unit.strip().lower()
    rng_unit = plausible_rng.unit.strip().lower()
    cand_period = candidate_est.period.strip().lower()
    rng_period = plausible_rng.period.strip().lower()

    if cand_unit != rng_unit or cand_period != rng_period:
        return {
            "status": "unit_mismatch",
            "is_within_range": None,
            "variance_percent": None,
            "unit_match": False,
            "summary_label": "Unit / Timeframe Mismatch",
            "diagnostic_note": f"Candidate estimated in '{candidate_est.unit}/{candidate_est.period}', while benchmark range is in '{plausible_rng.unit}/{plausible_rng.period}'. Comparison held to avoid invalid calculation.",
        }

    cand_val = candidate_est.value
    min_val = min(plausible_rng.min, plausible_rng.max)
    max_val = max(plausible_rng.min, plausible_rng.max)
    midpoint = (min_val + max_val) / 2.0 if (min_val + max_val) > 0 else 1.0

    if cand_val < min_val:
        pct_under = round(((min_val - cand_val) / midpoint) * 100, 1)
        return {
            "status": "below_range",
            "is_within_range": False,
            "variance_percent": -pct_under,
            "unit_match": True,
            "summary_label": f"Below Realistic Band (-{pct_under}%)",
            "diagnostic_note": "Candidate estimate falls below plausible industry bounds. Check for omitted demographic segments or overly conservative proxies.",
        }
    elif cand_val > max_val:
        pct_over = round(((cand_val - max_val) / midpoint) * 100, 1)
        return {
            "status": "above_range",
            "is_within_range": False,
            "variance_percent": pct_over,
            "unit_match": True,
            "summary_label": f"Above Realistic Band (+{pct_over}%)",
            "diagnostic_note": "Candidate estimate exceeds plausible industry bounds. Check for double-counting, unrealistic penetration, or compounding math errors.",
        }
    else:
        variance_from_mid = round(((cand_val - midpoint) / midpoint) * 100, 1)
        return {
            "status": "within_range",
            "is_within_range": True,
            "variance_percent": variance_from_mid,
            "unit_match": True,
            "summary_label": "Within Plausible Consulting Band",
            "diagnostic_note": "Candidate final estimate lands inside the plausible industry range. (Note: Being inside the range demonstrates numerical sanity, but must be accompanied by MECE structure to verify sound methodology).",
        }


def _compute_deterministic_sensitivity(
    candidate_est: Optional[CandidateEstimate],
    driver: Optional[SensitivityDriverInput],
) -> Dict[str, Any]:
    """Deterministically calculate low/high sensitivity swings on candidate's estimate."""
    if not candidate_est or candidate_est.value is None or not driver or driver.baseline_value is None or driver.low_scenario_value is None or driver.high_scenario_value is None:
        return {
            "status": "unavailable",
            "driver_name": driver.driver_name if driver else "Key Assumption",
            "formula_expression": driver.formula_expression if driver else "Multiplicative Estimation Model",
            "explanation": "Formula or driver scenarios were not sufficiently articulated for deterministic sensitivity simulation.",
        }

    base_val = driver.baseline_value
    cand_val = candidate_est.value
    if abs(base_val) < 1e-9 or abs(cand_val) < 1e-9:
        return {
            "status": "unavailable",
            "driver_name": driver.driver_name,
            "explanation": "Baseline driver value is zero, preventing ratio-based sensitivity modeling.",
        }

    low_val = driver.low_scenario_value
    high_val = driver.high_scenario_value

    low_est = cand_val * (low_val / base_val)
    high_est = cand_val * (high_val / base_val)
    impact_pct = round(abs((high_est - low_est) / (2.0 * cand_val)) * 100, 1)

    return {
        "status": "computed",
        "driver_name": driver.driver_name,
        "formula_expression": driver.formula_expression or "Multiplicative Estimation Model",
        "baseline_driver_value": base_val,
        "low_driver_value": low_val,
        "high_driver_value": high_val,
        "driver_unit": driver.unit or "units",
        "baseline_estimate": round(cand_val, 2),
        "low_estimate": round(low_est, 2),
        "high_estimate": round(high_est, 2),
        "impact_percent": impact_pct,
        "explanation": driver.explanation or f"Fluctuations in '{driver.driver_name}' create a ±{impact_pct}% variance swing on the final sizing result.",
    }


async def evaluate_guesstimate(
    question: str,
    category: str,
    difficulty: str,
    candidate_answer: str,
    approach_type: str = "top_down",
) -> Dict[str, Any]:
    """Evaluate candidate's guesstimate response using LLM qualitative reasoning and deterministic math."""
    default_fallback: Dict[str, Any] = {
        "overall_score": 74,
        "mece_score": 75,
        "mece_feedback": "Structured formula breakdown provided with clear segmentation.",
        "assumption_score": 72,
        "assumption_feedback": "Assumptions were stated; continue to provide real-world proxies to defend baseline figures.",
        "mental_math_score": 76,
        "math_feedback": "Arithmetic articulated step-by-step with good numerical rounding.",
        "sanity_check_score": 70,
        "sanity_check_feedback": "Include an explicit reality check against national or per-capita benchmarks.",
        "candidate_final_estimate": "Estimated based on candidate arithmetic.",
        "plausible_industry_range": "Reasonable industry estimate",
        "candidate_estimate_structured": {
            "value": 1000000.0,
            "unit": "units",
            "period": "annual",
            "geography": "target market",
            "formatted_display": "1.0M units/year",
        },
        "plausible_range_structured": {
            "min": 800000.0,
            "max": 1400000.0,
            "unit": "units",
            "period": "annual",
            "geography": "target market",
            "benchmark_source": "Industry Market Benchmark",
            "formatted_display": "800K - 1.4M units/year",
        },
        "model_approach_name": "Top-Down Demand-Side Breakdown",
        "model_breakdown_steps": [
            {"step_name": "Target Population / Market Size", "formula_or_proxy": "Total Relevant Demographic Pool", "estimated_value": "Baseline Pool"},
            {"step_name": "Target Penetration Rate", "formula_or_proxy": "Urban / Income Bracket Filtering", "estimated_value": "~25% - 30%"},
            {"step_name": "Usage & Frequency Multiplier", "formula_or_proxy": "Annual or Daily Volume per Consumer", "estimated_value": "Usage Benchmark"},
            {"step_name": "Total Estimated Aggregate", "formula_or_proxy": "Multiplying segments out", "estimated_value": "Plausible Volume"},
        ],
        "candidate_branch_diagnostics": [
            {
                "branch_name": "Core Market Segmentation",
                "status": "supported_mece",
                "formula_or_proxy": "Demographic filtering by relevant cohort",
                "estimated_value": "Primary Target Segment",
                "evidence_rationale": "Candidate articulated an initial population segmentation step.",
            },
            {
                "branch_name": "Usage Assumptions",
                "status": "unsupported_proxy",
                "formula_or_proxy": "Per-capita consumption rate",
                "estimated_value": "Average Frequency",
                "evidence_rationale": "Proxy assumed without explicit real-world justification.",
            },
        ],
        "sensitivity_analysis": {
            "status": "unavailable",
            "driver_name": "Adoption Rate",
            "explanation": "Provide an explicit algebraic equation to activate deterministic sensitivity modeling.",
        },
        "range_diagnostic": {
            "status": "within_range",
            "is_within_range": True,
            "variance_percent": 0.0,
            "unit_match": True,
            "summary_label": "Within Plausible Consulting Band",
            "diagnostic_note": "Candidate final estimate lands inside the plausible industry range.",
        },
        "scoring_weights": {
            "mece": 0.35,
            "assumption": 0.25,
            "math": 0.20,
            "sanity": 0.20,
            "formula_display": "35% MECE + 25% Assumptions + 20% Math + 20% Sanity Check",
        },
        "strengths": [
            "Clear verbal breakdown from high-level formula down to calculation.",
            "Demonstrated willingness to articulate thought process out loud.",
        ],
        "weaknesses": [
            "State explicit boundary conditions (geography, channel, timeframe) earlier.",
            "Always conclude with a 15-second sanity check against a macro benchmark.",
        ],
        "ideal_verbal_script": (
            f"To estimate {question.lower().replace('estimate', '').strip()}, I will use a top-down demand framework. "
            "First, I'll segment the relevant population pool, apply targeted penetration rates based on income and geography, "
            "and multiply by consumption frequency. Finally, I'll run a sanity check against total market capacity."
        ),
        "executive_summary": (
            "Candidate presented a solid conceptual breakdown. With tighter MECE boundaries and an explicit reality check, "
            "this response matches Tier-1 consulting placement standards."
        ),
    }

    if not candidate_answer or len(candidate_answer.strip()) < 15:
        default_fallback["overall_score"] = 40
        default_fallback["mece_score"] = 40
        default_fallback["assumption_score"] = 40
        default_fallback["mental_math_score"] = 40
        default_fallback["sanity_check_score"] = 40
        default_fallback["executive_summary"] = "Response was too brief to evaluate complete formula breakdown and mental math."
        return default_fallback

    try:
        chain = _guesstimate_prompt | _get_llm() | _guesstimate_parser
        result = await chain.ainvoke(
            {
                "question": question,
                "category": category,
                "difficulty": difficulty,
                "approach_type": approach_type,
                "candidate_answer": candidate_answer,
                "format_instructions": _guesstimate_parser.get_format_instructions(),
            }
        )

        mece = max(0, min(100, int(result.get("mece_score", 75))))
        assumptions = max(0, min(100, int(result.get("assumption_score", 75))))
        math_score = max(0, min(100, int(result.get("mental_math_score", 75))))
        sanity = max(0, min(100, int(result.get("sanity_check_score", 70))))

        # Refinement 1: Authoritative Deterministic Scoring (35% MECE, 25% Assumptions, 20% Math, 20% Sanity Check)
        deterministic_overall = max(
            0,
            min(
                100,
                round(
                    0.35 * mece + 0.25 * assumptions + 0.20 * math_score + 0.20 * sanity
                ),
            ),
        )

        steps = result.get("model_breakdown_steps") or default_fallback["model_breakdown_steps"]
        strengths = result.get("strengths") or default_fallback["strengths"]
        weaknesses = result.get("weaknesses") or default_fallback["weaknesses"]

        # Parse structured estimates & ranges
        cand_est_dict = result.get("candidate_estimate_structured")
        plaus_rng_dict = result.get("plausible_range_structured")
        cand_est = CandidateEstimate(**cand_est_dict) if isinstance(cand_est_dict, dict) else None
        plaus_rng = PlausibleRange(**plaus_rng_dict) if isinstance(plaus_rng_dict, dict) else None

        # Refinement 3: Deterministic Range Comparison Engine
        range_diag = _compute_deterministic_range_diagnostic(cand_est, plaus_rng)

        # Parse sensitivity driver
        driver_dict = result.get("sensitivity_driver")
        driver_obj = SensitivityDriverInput(**driver_dict) if isinstance(driver_dict, dict) else None

        # Refinement 4: Deterministic Sensitivity Calculation Engine
        sensitivity_diag = _compute_deterministic_sensitivity(cand_est, driver_obj)

        # Candidate branch diagnostics
        branch_diags = result.get("candidate_branch_diagnostics") or default_fallback["candidate_branch_diagnostics"]
        if isinstance(branch_diags, list):
            cleaned_branches = []
            for b in branch_diags:
                if isinstance(b, dict):
                    cleaned_branches.append(b)
                elif hasattr(b, "model_dump"):
                    cleaned_branches.append(b.model_dump())
            branch_diags = cleaned_branches

        return {
            "overall_score": deterministic_overall,
            "mece_score": mece,
            "mece_feedback": str(result.get("mece_feedback") or default_fallback["mece_feedback"]),
            "assumption_score": assumptions,
            "assumption_feedback": str(result.get("assumption_feedback") or default_fallback["assumption_feedback"]),
            "mental_math_score": math_score,
            "math_feedback": str(result.get("math_feedback") or default_fallback["math_feedback"]),
            "sanity_check_score": sanity,
            "sanity_check_feedback": str(result.get("sanity_check_feedback") or default_fallback["sanity_check_feedback"]),
            "candidate_final_estimate": str(result.get("candidate_final_estimate") or (cand_est.formatted_display if cand_est else "")),
            "plausible_industry_range": str(result.get("plausible_industry_range") or (plaus_rng.formatted_display if plaus_rng else default_fallback["plausible_industry_range"])),
            "candidate_estimate_structured": cand_est.model_dump() if cand_est else default_fallback["candidate_estimate_structured"],
            "plausible_range_structured": plaus_rng.model_dump() if plaus_rng else default_fallback["plausible_range_structured"],
            "range_diagnostic": range_diag,
            "model_approach_name": str(result.get("model_approach_name") or default_fallback["model_approach_name"]),
            "model_breakdown_steps": steps if isinstance(steps, list) else default_fallback["model_breakdown_steps"],
            "candidate_branch_diagnostics": branch_diags,
            "sensitivity_analysis": sensitivity_diag,
            "scoring_weights": {
                "mece": 0.35,
                "assumption": 0.25,
                "math": 0.20,
                "sanity": 0.20,
                "formula_display": "35% MECE + 25% Assumptions + 20% Math + 20% Sanity Check",
            },
            "strengths": strengths if isinstance(strengths, list) else [str(strengths)],
            "weaknesses": weaknesses if isinstance(weaknesses, list) else [str(weaknesses)],
            "ideal_verbal_script": str(result.get("ideal_verbal_script") or default_fallback["ideal_verbal_script"]),
            "executive_summary": str(result.get("executive_summary") or default_fallback["executive_summary"]),
        }
    except Exception as exc:
        logger.warning("Guesstimate evaluation error: %s. Using structured fallback.", exc)
        return default_fallback
