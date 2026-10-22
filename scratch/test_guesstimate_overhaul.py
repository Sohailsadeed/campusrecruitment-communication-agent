"""Acceptance validation script for Guesstimate 4-rubric overhaul & numerical invariants."""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.guesstimate.evaluator import (
    evaluate_guesstimate,
    _round_half_up,
    _compute_deterministic_range_diagnostic,
    _compute_deterministic_sensitivity,
    CandidateEstimate,
    PlausibleRange,
    SensitivityDriverInput,
)

async def test_deterministic_evaluator():
    print("--- 1. Testing Deliberate Rounding Policy (Conventional Half-Up) ---")
    # Conventional half-up: 82.5 -> 83 (unlike Python Banker's round which gives 82)
    val_half = 0.35 * 90 + 0.25 * 80 + 0.20 * 75 + 0.20 * 80  # 31.5 + 20 + 15 + 16 = 82.5
    rounded = _round_half_up(val_half)
    assert rounded == 83, f"Expected conventional half-up 83, got {rounded}"
    print(f"[OK] Conventional half-up policy verified: {val_half} -> {rounded}")

    print("\n--- 2. Testing Range Variance Definition & Midpoint Documentation ---")
    cand_est = CandidateEstimate(value=1200000, unit="units", period="annual", geography="US", formatted_display="1.2M units/yr")
    plaus_rng = PlausibleRange(min=1000000, max=1500000, unit="units", period="annual", geography="US", formatted_display="1.0M - 1.5M units/yr")
    diag = _compute_deterministic_range_diagnostic(cand_est, plaus_rng)
    assert diag["status"] == "within_range"
    assert diag["variance_reference"] == "range_midpoint"
    assert diag["range_midpoint"] == 1250000.0
    # (1200000 - 1250000) / 1250000 * 100 = -4.0%
    assert diag["variance_percent"] == -4.0
    print(f"[OK] Range variance documented: {diag['variance_formula']} -> {diag['variance_percent']}% relative to midpoint {diag['range_midpoint']}")

    print("\n--- 3. Testing Direction-Aware Sensitivity Engine ---")
    # Case A: Inverse Relationship (e.g. Replacement Cycle in Denominator: E = H / R)
    driver_inv = SensitivityDriverInput(
        driver_name="Household Replacement Cycle",
        baseline_value=4.0,
        low_scenario_value=3.0,
        high_scenario_value=5.0,
        unit="years",
        is_inverse_relationship=True,
        formula_expression="Total = Households * (1 / Replacement Cycle)"
    )
    sens_inv = _compute_deterministic_sensitivity(cand_est, driver_inv)
    assert sens_inv["status"] == "computed"
    assert sens_inv["is_inverse_relationship"] is True
    # In inverse model:
    # 5.0 years in denominator gives FLOOR: 1.2M * (4/5) = 960,000 (-20.0%)
    # 3.0 years in denominator gives CEILING: 1.2M * (4/3) = 1,600,000 (+33.3%)
    assert sens_inv["conservative_scenario"]["driver_value"] == 5.0
    assert sens_inv["conservative_scenario"]["resulting_estimate"] == 960000.0
    assert sens_inv["conservative_scenario"]["delta_percent"] == -20.0
    assert sens_inv["aggressive_scenario"]["driver_value"] == 3.0
    assert sens_inv["aggressive_scenario"]["resulting_estimate"] == 1600000.0
    assert sens_inv["aggressive_scenario"]["delta_percent"] == 33.3
    print(f"[OK] Inverse denominator driver verified:")
    print(f"     Floor: {sens_inv['conservative_scenario']['label']} -> {sens_inv['conservative_scenario']['resulting_estimate']}")
    print(f"     Ceiling: {sens_inv['aggressive_scenario']['label']} -> {sens_inv['aggressive_scenario']['resulting_estimate']}")

    # Case A.2: Direct E = H / R representation with driver symbol R
    driver_ehr = SensitivityDriverInput(
        driver_name="R (Replacement Cycle)",
        baseline_value=4.0,
        low_scenario_value=3.0,
        high_scenario_value=5.0,
        unit="years",
        relationship_type="inverse_denominator",
        variable_role="denominator_divisor",
        formula_expression="E = H / R"
    )
    sens_ehr = _compute_deterministic_sensitivity(cand_est, driver_ehr)
    assert sens_ehr["status"] == "computed"
    assert sens_ehr["is_inverse_relationship"] is True
    assert sens_ehr["validation_tier"] == "validated_formula"
    assert sens_ehr["conservative_scenario"]["driver_value"] == 5.0
    assert sens_ehr["aggressive_scenario"]["driver_value"] == 3.0
    print(f"[OK] Explicit E = H / R inverse formula verified with isolated denominator divisor.")

    # Case B: Direct Multiplier Relationship (e.g. Adoption Rate: E = Population * Adoption)
    driver_dir = SensitivityDriverInput(
        driver_name="Market Adoption Rate",
        baseline_value=0.20,
        low_scenario_value=0.15,
        high_scenario_value=0.30,
        unit="ratio",
        is_inverse_relationship=False,
        formula_expression="Total = Pool * Adoption Rate"
    )
    sens_dir = _compute_deterministic_sensitivity(cand_est, driver_dir)
    assert sens_dir["status"] == "computed"
    assert sens_dir["is_inverse_relationship"] is False
    # 0.15 gives floor: 1.2M * (0.15/0.20) = 900,000 (-25.0%)
    # 0.30 gives ceiling: 1.2M * (0.30/0.20) = 1,800,000 (+50.0%)
    assert sens_dir["conservative_scenario"]["driver_value"] == 0.15
    assert sens_dir["conservative_scenario"]["resulting_estimate"] == 900000.0
    assert sens_dir["aggressive_scenario"]["driver_value"] == 0.30
    assert sens_dir["aggressive_scenario"]["resulting_estimate"] == 1800000.0
    # Case C: Keyword "replacement cycle" in Multiplicative Formula (E = Demand * Replacement_Cycle)
    # The formula representation MUST take precedence over naive keyword heuristics!
    driver_mult_kw = SensitivityDriverInput(
        driver_name="Replacement Cycle Factor",
        baseline_value=2.0,
        low_scenario_value=1.5,
        high_scenario_value=2.5,
        unit="factor",
        variable_role="numerator_factor",
        is_inverse_relationship=False,
        formula_expression="Total = Baseline_Demand * Replacement Cycle Factor"
    )
    sens_mult_kw = _compute_deterministic_sensitivity(cand_est, driver_mult_kw)
    assert sens_mult_kw["status"] == "computed"
    assert sens_mult_kw["is_inverse_relationship"] is False, "Formula representation should override keyword heuristic!"
    assert sens_mult_kw["validation_tier"] == "validated_formula"
    print(f"[OK] Formula representation overrides keyword heuristic: purely multiplicative verified as direct.")

    # Case D: Complex Formula with Additive Offsets (E = (H * P) / R + Fixed_Fleet)
    # Additive terms prevent ceteris paribus ratio sensitivity -> must trigger ambiguity guard!
    driver_complex = SensitivityDriverInput(
        driver_name="Household Replacement Cycle",
        baseline_value=4.0,
        low_scenario_value=3.0,
        high_scenario_value=5.0,
        unit="years",
        relationship_type="inverse_denominator",
        formula_expression="Total = (Households * Penetration) / Replacement_Cycle + Fixed_Fleet_Demand"
    )
    sens_complex = _compute_deterministic_sensitivity(cand_est, driver_complex)
    assert sens_complex["status"] == "insufficient_formula_articulation", "Complex multi-term formulas must NOT produce misleading estimates!"
    assert sens_complex["validation_tier"] == "complex_formula"
    print(f"[OK] Complex formula with additive terms safely held: {sens_complex['explanation']}")

    # Case E: Ambiguous or Unspecified Formula
    driver_ambig = SensitivityDriverInput(
        driver_name="Macro Multiplier",
        baseline_value=1.5,
        low_scenario_value=1.2,
        high_scenario_value=1.8,
        unit="index",
        relationship_type="ambiguous",
        formula_expression="Unclear interplay"
    )
    sens_ambig = _compute_deterministic_sensitivity(cand_est, driver_ambig)
    # Case F: Multi-Driver Tornado Comparison Ranking
    # Primary lever: Replacement Cycle (±26.7% swing)
    # Secondary lever: Target Penetration Rate (±15.0% swing)
    driver_primary = SensitivityDriverInput(
        driver_name="Replacement Cycle",
        baseline_value=4.0,
        low_scenario_value=3.0,
        high_scenario_value=5.0,
        unit="years",
        relationship_type="inverse_denominator",
        variable_role="denominator_divisor",
        formula_expression="Total = Pool / Replacement_Cycle"
    )
    driver_secondary = SensitivityDriverInput(
        driver_name="Target Penetration Rate",
        baseline_value=0.20,
        low_scenario_value=0.17,
        high_scenario_value=0.23,
        unit="ratio",
        relationship_type="direct_multiplier",
        variable_role="numerator_factor",
        formula_expression="Total = Pool * Penetration Rate"
    )
    sens_tornado = _compute_deterministic_sensitivity(cand_est, driver_primary, driver_secondary)
    assert sens_tornado["status"] == "computed"
    assert sens_tornado["has_multi_driver_comparison"] is True
    assert len(sens_tornado["tornado_ranking"]) == 2
    assert sens_tornado["tornado_ranking"][0]["rank"] == 1
    assert sens_tornado["tornado_ranking"][0]["driver_name"] == "Replacement Cycle"
    assert sens_tornado["tornado_ranking"][1]["rank"] == 2
    assert sens_tornado["tornado_ranking"][1]["driver_name"] == "Target Penetration Rate"
    assert sens_tornado["leverage_ratio"] >= 1.5
    print(f"[OK] Multi-driver tornado ranking verified: #{1} {sens_tornado['tornado_ranking'][0]['driver_name']} (±{sens_tornado['tornado_ranking'][0]['impact_percent']}%) vs #{2} {sens_tornado['tornado_ranking'][1]['driver_name']} (±{sens_tornado['tornado_ranking'][1]['impact_percent']}%), ratio={sens_tornado['leverage_ratio']}x")

    print("\n--- 4. Testing End-to-End Fallback Schema Contract ---")
    fallback_res = await evaluate_guesstimate(
        question="Estimate annual market for EV chargers",
        category="Market Sizing",
        difficulty="Intermediate",
        candidate_answer="Too brief",
        approach_type="top_down"
    )
    assert fallback_res["overall_score"] == 40
    print(f"[OK] Fallback score={fallback_res['overall_score']}")

    print("\nALL INVARIANTS RIGOROUSLY VALIDATED!")

if __name__ == "__main__":
    asyncio.run(test_deterministic_evaluator())
