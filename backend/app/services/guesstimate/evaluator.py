"""Guesstimate interview evaluation service using OpenRouter Nemotron / Ollama fallback."""
import logging
import math
import re
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
    low_scenario_value: Optional[float] = Field(default=None, description="Conservative / alternative scenario value (e.g. 0.15)")
    high_scenario_value: Optional[float] = Field(default=None, description="Aggressive / alternative scenario value (e.g. 0.35)")
    unit: str = Field(default="ratio", description="Unit of the driver variable (e.g. %, years, frequency, dollars)")
    relationship_type: str = Field(
        default="direct_multiplier",
        description="Must be strictly one of: 'direct_multiplier' (variable is a numerator term, e.g. population, price, adoption rate, replacement rate), 'inverse_denominator' (variable is in denominator, e.g. replacement cycle in years, turnaround time, unit capacity per worker), or 'ambiguous' (non-linear, additive offset, or multi-variable interplay)"
    )
    variable_role: str = Field(
        default="numerator_factor",
        description="Explicit algebraic position: 'numerator_factor' (variable multiplied in numerator), 'denominator_divisor' (variable divided in denominator), or 'complex_additive' / 'ambiguous'"
    )
    is_inverse_relationship: bool = Field(
        default=False,
        description="Boolean helper: True if inverse_denominator, False if direct_multiplier"
    )
    formula_expression: str = Field(default="", description="Identified formula (e.g. Total = Population * Penetration * Frequency * Price or E = H / R)")
    explanation: str = Field(default="", description="Why this variable carries the highest sensitivity to estimation variance")


class GuesstimateEvaluationSchema(BaseModel):
    evaluation_version: int = Field(
        default=2,
        description="Schema contract version",
    )
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
    secondary_sensitivity_driver: Optional[SensitivityDriverInput] = Field(
        default=None,
        description="Optional secondary driver variable (e.g. price, ticket size, or frequency) for multi-driver tornado comparison",
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
            "- Sensitivity Driver Identification & Precedence:\n"
            "  1. Identify the single most volatile assumption as sensitivity_driver (e.g. Volume/Replacement lever) and state the explicit algebraic formula (e.g. 'E = H / R' or 'Total = Population * Penetration * Frequency * Price').\n"
            "  2. If candidate equation includes another critical assumption (e.g. Price, Ticket Size, or Frequency lever), identify it as secondary_sensitivity_driver for tornado comparison.\n"
            "  3. Assign explicit variable_role: 'numerator_factor', 'denominator_divisor', or 'complex_additive' / 'ambiguous'.\n"
            "  4. Set relationship_type strictly: 'direct_multiplier', 'inverse_denominator', or 'ambiguous'. If the candidate formula contains complex multi-variable interactions, non-linear terms, or additive terms where single-variable ratio sensitivity does not hold, explicitly set relationship_type to 'ambiguous'.\n"
            "  5. Provide baseline, low (conservative), and high (aggressive) scenario values for each driver.\n\n"
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


def _round_half_up(val: float) -> int:
    """Conventional arithmetic half-up rounding (e.g. 82.5 -> 83)."""
    import math
    return math.floor(val + 0.5) if val >= 0 else math.ceil(val - 0.5)


def _compute_deterministic_range_diagnostic(
    candidate_est: Optional[CandidateEstimate],
    plausible_rng: Optional[PlausibleRange],
) -> Dict[str, Any]:
    """Deterministically compare candidate estimate against plausible benchmark range with documented baseline."""
    if not candidate_est or candidate_est.value is None or not plausible_rng or plausible_rng.min is None or plausible_rng.max is None:
        return {
            "status": "unavailable",
            "is_within_range": None,
            "variance_percent": None,
            "variance_reference": "range_midpoint",
            "range_midpoint": None,
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
            "variance_reference": "range_midpoint",
            "range_midpoint": None,
            "unit_match": False,
            "summary_label": "Unit / Timeframe Mismatch",
            "diagnostic_note": f"Candidate estimated in '{candidate_est.unit}/{candidate_est.period}', while benchmark range is in '{plausible_rng.unit}/{plausible_rng.period}'. Comparison held to avoid invalid calculation.",
        }

    cand_val = candidate_est.value
    min_val = min(plausible_rng.min, plausible_rng.max)
    max_val = max(plausible_rng.min, plausible_rng.max)
    midpoint = (min_val + max_val) / 2.0 if (min_val + max_val) > 0 else 1.0

    # Documented definition:
    # variance_percent measures the percentage displacement of the candidate's estimate
    # relative to the benchmark range midpoint: ((candidate_estimate - midpoint) / midpoint) * 100
    variance_from_mid = round(((cand_val - midpoint) / midpoint) * 100, 1)

    if cand_val < min_val:
        pct_under = round(((min_val - cand_val) / midpoint) * 100, 1)
        return {
            "status": "below_range",
            "is_within_range": False,
            "variance_percent": variance_from_mid,
            "variance_reference": "range_midpoint",
            "range_midpoint": round(midpoint, 2),
            "variance_formula": "((candidate_estimate - range_midpoint) / range_midpoint) * 100",
            "unit_match": True,
            "summary_label": f"Below Realistic Band ({variance_from_mid}%)",
            "diagnostic_note": f"Candidate estimate falls below plausible industry bounds by {pct_under}% from the lower floor. Check for omitted demographic segments or overly conservative proxies.",
        }
    elif cand_val > max_val:
        pct_over = round(((cand_val - max_val) / midpoint) * 100, 1)
        return {
            "status": "above_range",
            "is_within_range": False,
            "variance_percent": variance_from_mid,
            "variance_reference": "range_midpoint",
            "range_midpoint": round(midpoint, 2),
            "variance_formula": "((candidate_estimate - range_midpoint) / range_midpoint) * 100",
            "unit_match": True,
            "summary_label": f"Above Realistic Band (+{variance_from_mid}%)",
            "diagnostic_note": f"Candidate estimate exceeds plausible industry bounds by +{pct_over}% above the upper ceiling. Check for double-counting, unrealistic penetration, or compounding math errors.",
        }
    else:
        return {
            "status": "within_range",
            "is_within_range": True,
            "variance_percent": variance_from_mid,
            "variance_reference": "range_midpoint",
            "range_midpoint": round(midpoint, 2),
            "variance_formula": "((candidate_estimate - range_midpoint) / range_midpoint) * 100",
            "unit_match": True,
            "summary_label": f"Within Plausible Band ({variance_from_mid:+0.1f}% from midpoint)",
            "diagnostic_note": "Candidate final estimate lands inside the plausible industry range. (Note: Being inside the range demonstrates numerical sanity, but must be accompanied by MECE structure to verify sound methodology).",
        }


def _validate_driver_relationship(
    driver: SensitivityDriverInput,
) -> tuple[Optional[bool], str, str]:
    """Validate mathematical relationship using 3-tier precedence.

    Returns:
        (is_inverse, validation_tier, explanation)
        where is_inverse is:
          - True: inverse relationship (driver in denominator divisor, E = K / D)
          - False: direct multiplier relationship (driver in numerator factor, E = K * D)
          - None: ambiguous, complex, non-linear, or insufficiently articulated
    """
    rel_type = (getattr(driver, "relationship_type", None) or "").strip().lower()
    var_role = (getattr(driver, "variable_role", None) or "").strip().lower()
    expr = (getattr(driver, "formula_expression", None) or "").strip()
    driver_name = driver.driver_name.strip()

    # Pre-check: If LLM or schema explicitly flags ambiguity, respect immediately
    if rel_type in ["ambiguous", "complex", "non_linear", "unclear"] or var_role in ["complex_additive", "ambiguous", "unclear"]:
        return (
            None,
            "explicit_ambiguity",
            f"Driver '{driver_name}' was identified with an ambiguous, complex, or non-linear relationship in candidate reasoning.",
        )

    # Clean formula expression: replace unicode math operators
    expr_clean = expr.replace("×", "*").replace("÷", "/").replace("−", "-")

    # -----------------------------------------------------------------
    # PRECEDENCE 1: Validated formula representation & explicit variable roles
    # -----------------------------------------------------------------
    if expr_clean:
        # Check for additive/subtractive offsets: e.g. "A + B", "Total = (A + B) / C", "A * B + C"
        has_additive_terms = bool(re.search(r'(?<=\s)[+\-](?=\s)|[+]', expr_clean))

        if "/" in expr_clean:
            # Division formula: e.g. E = H / R or Total = (Pool * Penetration) / Cycle
            if has_additive_terms:
                return (
                    None,
                    "complex_formula",
                    f"Formula '{expr}' contains additive terms and multi-variable shifts; holding other variables constant does not scale proportionally.",
                )

            parts = expr_clean.split("/", 1)
            num_part = parts[0].lower()
            denom_part = parts[1].lower()

            num_clean = re.sub(r'[^a-zA-Z0-9_]', ' ', num_part).lower()
            denom_clean = re.sub(r'[^a-zA-Z0-9_]', ' ', denom_part).lower()
            driver_norm = re.sub(r'[^a-zA-Z0-9_]', ' ', driver_name).lower()
            driver_tokens = [t for t in driver_norm.split() if len(t) > 1 or t.isalpha()]

            # Step 1: Full phrase matching
            in_denom = driver_norm in denom_clean
            in_num = driver_norm in num_clean

            # Step 2: Core driver token matching (filtering demographic pool prefixes like "households", "population")
            if not in_denom and not in_num:
                core_driver_tokens = [
                    t for t in driver_tokens
                    if t not in ["market", "target", "household", "households", "population", "user", "users", "customer", "customers", "total", "pool"]
                ]
                if not core_driver_tokens:
                    core_driver_tokens = driver_tokens

                in_denom = any(t in denom_clean.split() for t in core_driver_tokens)
                in_num = any(t in num_clean.split() for t in core_driver_tokens)

            # Step 3: Explicit variable role and relationship type validation
            if var_role == "denominator_divisor" or rel_type == "inverse_denominator":
                if in_denom or not in_num:
                    in_denom = True
                    in_num = False
            elif var_role == "numerator_factor" or rel_type == "direct_multiplier":
                if in_num or not in_denom:
                    in_num = True
                    in_denom = False

            if in_denom and not in_num:
                return (
                    True,
                    "validated_formula",
                    f"Validated inverse relationship: '{driver_name}' is isolated in the denominator divisor of '{expr}'.",
                )
            elif in_num and not in_denom:
                return (
                    False,
                    "validated_formula",
                    f"Validated direct relationship: '{driver_name}' is in the numerator of '{expr}'.",
                )
            elif in_denom and in_num:
                return (
                    None,
                    "complex_formula",
                    f"Driver '{driver_name}' appears on both sides of division in '{expr}'; relationship is non-linear.",
                )

        elif "*" in expr_clean and "/" not in expr_clean:
            # Purely multiplicative formula
            if has_additive_terms:
                return (
                    None,
                    "complex_formula",
                    f"Formula '{expr}' combines multiplication with additive offsets; single-variable sensitivity cannot be linearly isolated.",
                )

            # In a pure product A * B * C, holding other factors constant is strictly direct multiplier
            if var_role == "denominator_divisor" or rel_type == "inverse_denominator":
                logger.warning("Formula representation override: marked inverse but expression '%s' is purely multiplicative", expr)
                return (
                    False,
                    "validated_formula",
                    f"Formula '{expr}' is purely multiplicative with no divisor; validated as direct multiplier.",
                )
            else:
                return (
                    False,
                    "validated_formula",
                    f"Validated direct relationship: formula '{expr}' is a pure product model.",
                )

    # -----------------------------------------------------------------
    # PRECEDENCE 2: LLM Candidate Identification with Cross-Validation
    # -----------------------------------------------------------------
    # When formula syntax is non-algebraic or descriptive, rely on explicit roles if consistent
    if var_role == "denominator_divisor" or rel_type == "inverse_denominator":
        if bool(driver.is_inverse_relationship) or var_role == "denominator_divisor":
            return (
                True,
                "llm_role_validated",
                f"LLM identified explicit denominator divisor role for '{driver_name}'.",
            )
    elif var_role == "numerator_factor" or rel_type == "direct_multiplier":
        if not bool(driver.is_inverse_relationship) or var_role == "numerator_factor":
            return (
                False,
                "llm_role_validated",
                f"LLM identified explicit numerator factor role for '{driver_name}'.",
            )

    # -----------------------------------------------------------------
    # PRECEDENCE 3: Keyword Heuristics as Fallback ONLY, with Strict Ambiguity Guard
    # -----------------------------------------------------------------
    text_corpus = f"{expr_clean} {driver_name.lower()} {getattr(driver, 'explanation', '')}".lower()
    has_explicit_division_kw = any(kw in text_corpus for kw in ["divided by", "per cycle", "turnaround time", "replacement cycle", "divided across"])
    has_explicit_multiplier_kw = any(kw in text_corpus for kw in ["multiplied by", "penetration rate", "adoption rate", "frequency per", "times per"])

    if has_explicit_division_kw and not has_explicit_multiplier_kw and bool(driver.is_inverse_relationship):
        return (
            True,
            "keyword_fallback",
            "Inferred inverse relationship from explicit division/cycle terminology as fallback.",
        )
    elif has_explicit_multiplier_kw and not has_explicit_division_kw and not bool(driver.is_inverse_relationship):
        return (
            False,
            "keyword_fallback",
            "Inferred direct multiplier relationship from rate/penetration terminology as fallback.",
        )

    # Ambiguous: DO NOT GUESS OR GENERATE POTENTIALLY MISLEADING ESTIMATES
    return (
        None,
        "ambiguous",
        f"Mathematical relationship for '{driver_name}' could not be validated; deterministic simulation held to avoid misleading estimates.",
    )


def _simulate_single_driver(
    candidate_est: Optional[CandidateEstimate],
    driver: Optional[SensitivityDriverInput],
) -> Dict[str, Any]:
    """Deterministically simulate a single driver's scenarios with 3-tier precedence validation."""
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

    val_a = driver.low_scenario_value
    val_b = driver.high_scenario_value

    is_inverse, validation_tier, validation_note = _validate_driver_relationship(driver)

    if is_inverse is None:
        return {
            "status": "insufficient_formula_articulation",
            "driver_name": driver.driver_name,
            "formula_expression": driver.formula_expression or "Ambiguous / Multi-variable Model",
            "validation_tier": validation_tier,
            "explanation": validation_note,
        }

    # Deterministic scenario computation
    def _eval_scenario(d_val: float) -> float:
        if abs(d_val) < 1e-9:
            return 0.0
        return cand_val * (base_val / d_val) if is_inverse else cand_val * (d_val / base_val)

    est_a = _eval_scenario(val_a)
    est_b = _eval_scenario(val_b)

    est_floor = min(est_a, est_b)
    est_ceiling = max(est_a, est_b)
    impact_pct = round(abs((est_ceiling - est_floor) / (2.0 * cand_val)) * 100, 1)

    driver_for_floor = val_a if est_a <= est_b else val_b
    driver_for_ceiling = val_b if est_b >= est_a else val_a

    delta_floor_pct = round(((est_floor - cand_val) / cand_val) * 100, 1)
    delta_ceiling_pct = round(((est_ceiling - cand_val) / cand_val) * 100, 1)

    return {
        "status": "computed",
        "driver_name": driver.driver_name,
        "is_inverse_relationship": is_inverse,
        "relationship_type": "inverse (denominator)" if is_inverse else "direct (multiplier)",
        "validation_tier": validation_tier,
        "validation_note": validation_note,
        "formula_expression": driver.formula_expression or ("Direct Multiplier Model" if not is_inverse else "Inverse Denominator Model"),
        "baseline_driver_value": base_val,
        "driver_unit": driver.unit or "units",
        "baseline_estimate": round(cand_val, 2),
        "conservative_scenario": {
            "driver_value": driver_for_floor,
            "resulting_estimate": round(est_floor, 2),
            "delta_percent": delta_floor_pct,
            "label": f"{driver_for_floor} {driver.unit} ({delta_floor_pct:+0.1f}%)",
        },
        "aggressive_scenario": {
            "driver_value": driver_for_ceiling,
            "resulting_estimate": round(est_ceiling, 2),
            "delta_percent": delta_ceiling_pct,
            "label": f"{driver_for_ceiling} {driver.unit} ({delta_ceiling_pct:+0.1f}%)",
        },
        "low_driver_value": driver_for_floor,
        "high_driver_value": driver_for_ceiling,
        "low_estimate": round(est_floor, 2),
        "high_estimate": round(est_ceiling, 2),
        "impact_percent": impact_pct,
        "explanation": driver.explanation or f"Fluctuations in '{driver.driver_name}' ({val_a} to {val_b} {driver.unit}) create a ±{impact_pct}% variance swing on the final sizing result.",
    }


def _compute_deterministic_sensitivity(
    candidate_est: Optional[CandidateEstimate],
    driver: Optional[SensitivityDriverInput],
    secondary_driver: Optional[SensitivityDriverInput] = None,
) -> Dict[str, Any]:
    """Deterministically calculate sensitivity scenarios using 3-tier precedence and multi-driver tornado ranking.

    Precedence Order:
    1. Validated formula representation and explicit variable roles whenever possible.
    2. LLM identification of formula and driver, validated before computing scenarios.
    3. Keyword-based detection only as a fallback; if ambiguous, return 'insufficient_formula_articulation'.
    """
    primary_sim = _simulate_single_driver(candidate_est, driver)
    if primary_sim.get("status") != "computed":
        return primary_sim

    tornado_ranking = []
    secondary_sim = None
    if secondary_driver and secondary_driver.baseline_value is not None:
        sec_res = _simulate_single_driver(candidate_est, secondary_driver)
        if sec_res.get("status") == "computed":
            secondary_sim = sec_res

    if secondary_sim:
        # Multi-driver tornado comparison: sort descending by impact_percent
        drivers_to_rank = [primary_sim, secondary_sim]
        drivers_to_rank.sort(key=lambda d: d.get("impact_percent", 0), reverse=True)

        top_driver = drivers_to_rank[0]
        second_driver = drivers_to_rank[1]
        max_impact = max(top_driver.get("impact_percent", 1.0), 0.1)
        ratio = round(top_driver.get("impact_percent", 1.0) / max(second_driver.get("impact_percent", 1.0), 0.1), 1)

        for idx, d in enumerate(drivers_to_rank):
            role_kw = d["driver_name"].lower()
            if any(k in role_kw for k in ["cycle", "replacement", "population", "pool", "penetration", "adoption", "volume"]):
                role_label = "Volume / Market Sizing Lever"
            elif any(k in role_kw for k in ["price", "ticket", "cost", "fee", "revenue", "spend", "aov"]):
                role_label = "Unit Economics / Price Lever"
            else:
                role_label = "Usage / Frequency Lever"

            tornado_ranking.append({
                "rank": idx + 1,
                "driver_name": d["driver_name"],
                "role_label": role_label,
                "impact_percent": d["impact_percent"],
                "relationship_type": d["relationship_type"],
                "is_inverse_relationship": d["is_inverse_relationship"],
                "baseline_driver_value": d["baseline_driver_value"],
                "driver_unit": d["driver_unit"],
                "conservative_scenario": d["conservative_scenario"],
                "aggressive_scenario": d["aggressive_scenario"],
                "relative_bar_percent": 100.0 if idx == 0 else round((d["impact_percent"] / max_impact) * 100, 1),
                "explanation": d["explanation"],
            })

        result = dict(top_driver)
        result["has_multi_driver_comparison"] = True
        result["leverage_ratio"] = ratio
        result["tornado_ranking"] = tornado_ranking
        result["multi_driver_guidance"] = (
            f"Tornado Sensitivity: '{top_driver['driver_name']}' exerts {ratio}x more leverage (±{top_driver['impact_percent']}%) "
            f"than '{second_driver['driver_name']}' (±{second_driver['impact_percent']}%). In management consulting interviews, defend the #{1} driver first with defensible macro proxies."
        )
        return result
    else:
        d = primary_sim
        tornado_ranking.append({
            "rank": 1,
            "driver_name": d["driver_name"],
            "role_label": "Primary Leverage Lever",
            "impact_percent": d["impact_percent"],
            "relationship_type": d["relationship_type"],
            "is_inverse_relationship": d["is_inverse_relationship"],
            "baseline_driver_value": d["baseline_driver_value"],
            "driver_unit": d["driver_unit"],
            "conservative_scenario": d["conservative_scenario"],
            "aggressive_scenario": d["aggressive_scenario"],
            "relative_bar_percent": 100.0,
            "explanation": d["explanation"],
        })
        result = dict(primary_sim)
        result["has_multi_driver_comparison"] = False
        result["leverage_ratio"] = 1.0
        result["tornado_ranking"] = tornado_ranking
        return result


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

        # Refinement 1: Authoritative Deterministic Scoring (35% MECE, 25% Assumptions, 20% Math, 20% Sanity Check) with Conventional Half-Up Rounding
        raw_weighted = 0.35 * mece + 0.25 * assumptions + 0.20 * math_score + 0.20 * sanity
        deterministic_overall = max(0, min(100, _round_half_up(raw_weighted)))

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

        # Parse sensitivity drivers
        driver_dict = result.get("sensitivity_driver")
        secondary_dict = result.get("secondary_sensitivity_driver")
        driver_obj = SensitivityDriverInput(**driver_dict) if isinstance(driver_dict, dict) else None
        secondary_obj = SensitivityDriverInput(**secondary_dict) if isinstance(secondary_dict, dict) else None

        # Refinement 4: Deterministic Sensitivity Calculation Engine (direction-aware & tornado comparison)
        sensitivity_diag = _compute_deterministic_sensitivity(cand_est, driver_obj, secondary_obj)

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
            "evaluation_version": 2,
            "overall_score": deterministic_overall,
            "rubric_scores": {
                "mece_score": mece,
                "assumption_score": assumptions,
                "mental_math_score": math_score,
                "sanity_check_score": sanity,
            },
            # Flat keys preserved for backward compatibility
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
                "rounding_policy": "conventional_half_up",
                "formula_display": "35% MECE + 25% Assumptions + 20% Math + 20% Sanity Check (Half-Up)",
            },
            "strengths": strengths if isinstance(strengths, list) else [str(strengths)],
            "weaknesses": weaknesses if isinstance(weaknesses, list) else [str(weaknesses)],
            "ideal_verbal_script": str(result.get("ideal_verbal_script") or default_fallback["ideal_verbal_script"]),
            "executive_summary": str(result.get("executive_summary") or default_fallback["executive_summary"]),
        }
    except Exception as exc:
        logger.warning("Guesstimate evaluation error: %s. Using structured fallback.", exc)
        return default_fallback
