import { apiClient } from "./client";

export interface ModelTreeStep {
  step_name: string;
  formula_or_proxy: string;
  estimated_value: string;
}

export interface CandidateEstimateStructured {
  value?: number | null;
  unit?: string;
  period?: string;
  geography?: string;
  formatted_display?: string;
}

export interface PlausibleRangeStructured {
  min?: number | null;
  max?: number | null;
  unit?: string;
  period?: string;
  geography?: string;
  benchmark_source?: string;
  formatted_display?: string;
}

export interface RangeDiagnostic {
  status: "within_range" | "below_range" | "above_range" | "unit_mismatch" | "unavailable";
  is_within_range?: boolean | null;
  variance_percent?: number | null;
  unit_match?: boolean;
  summary_label: string;
  diagnostic_note: string;
}

export interface BranchEvidence {
  branch_name: string;
  status: "supported_mece" | "confirmed_overlap" | "omitted_segment" | "unsupported_proxy" | "unclear_evidence";
  formula_or_proxy: string;
  estimated_value: string;
  evidence_rationale: string;
}

export interface SensitivityScenario {
  driver_value: number;
  resulting_estimate: number;
  delta_percent: number;
  label: string;
}

export interface TornadoRankingItem {
  rank: number;
  driver_name: string;
  role_label: string;
  impact_percent: number;
  relationship_type: string;
  is_inverse_relationship: boolean;
  baseline_driver_value: number;
  driver_unit: string;
  conservative_scenario: SensitivityScenario;
  aggressive_scenario: SensitivityScenario;
  relative_bar_percent: number;
  explanation?: string;
}

export interface SensitivityAnalysis {
  status: "computed" | "unavailable" | "insufficient_formula_articulation";
  driver_name: string;
  formula_expression?: string;
  baseline_driver_value?: number;
  low_driver_value?: number;
  high_driver_value?: number;
  driver_unit?: string;
  baseline_estimate?: number;
  low_estimate?: number;
  high_estimate?: number;
  impact_percent?: number;
  conservative_scenario?: SensitivityScenario;
  aggressive_scenario?: SensitivityScenario;
  has_multi_driver_comparison?: boolean;
  leverage_ratio?: number;
  multi_driver_guidance?: string;
  tornado_ranking?: TornadoRankingItem[];
  explanation: string;
}

export interface GuesstimateEvaluation {
  overall_score: number;
  mece_score: number;
  mece_feedback: string;
  assumption_score: number;
  assumption_feedback: string;
  mental_math_score: number;
  math_feedback: string;
  sanity_check_score: number;
  sanity_check_feedback: string;
  candidate_final_estimate?: string;
  plausible_industry_range?: string;
  candidate_estimate_structured?: CandidateEstimateStructured | null;
  plausible_range_structured?: PlausibleRangeStructured | null;
  range_diagnostic?: RangeDiagnostic | null;
  candidate_branch_diagnostics?: BranchEvidence[];
  sensitivity_analysis?: SensitivityAnalysis | null;
  scoring_weights?: {
    mece: number;
    assumption: number;
    math: number;
    sanity: number;
    formula_display: string;
  };
  model_approach_name?: string;
  model_breakdown_steps?: ModelTreeStep[];
  strengths: string[];
  weaknesses: string[];
  ideal_verbal_script: string;
  executive_summary: string;
}

export interface GuesstimateSessionResponse {
  session_id: number;
  question: string;
  category: string;
  difficulty: string;
  approach_type: string;
  candidate_answer?: string;
  audio_url?: string;
  is_complete: boolean;
  overall_score?: number;
  evaluation?: GuesstimateEvaluation;
  created_at?: string;
}

export interface GuesstimateMetadataCategory {
  id: string;
  label: string;
  count: number;
}

export interface GuesstimateMetadataDifficulty {
  id: string;
  label: string;
  count: number;
}

export interface GuesstimateMetadataResponse {
  total_questions: number;
  categories: GuesstimateMetadataCategory[];
  difficulties: GuesstimateMetadataDifficulty[];
}

export async function getGuesstimateMetadata(): Promise<GuesstimateMetadataResponse> {
  const res = await apiClient.get<GuesstimateMetadataResponse>("/api/guesstimate/metadata");
  return res.data;
}

export async function getRandomGuesstimate(
  category?: string,
  difficulty?: string
): Promise<{ question: string; category: string; difficulty: string }> {
  const res = await apiClient.get("/api/guesstimate/random", {
    params: { category, difficulty },
  });
  return res.data;
}

export async function startGuesstimateSession(data: {
  category: string;
  difficulty: string;
  question?: string;
  approach_type?: string;
}): Promise<GuesstimateSessionResponse> {
  const res = await apiClient.post<GuesstimateSessionResponse>("/api/guesstimate/start", data);
  return res.data;
}

export async function submitGuesstimateAnswer(
  sessionId: number,
  answer: string,
  approachType: string = "top_down",
  audioBlob?: Blob | null
): Promise<{ session_id: number; overall_score: number; evaluation: GuesstimateEvaluation; audio_url?: string }> {
  const formData = new FormData();
  formData.append("session_id", String(sessionId));
  formData.append("answer", answer);
  formData.append("approach_type", approachType);
  if (audioBlob) {
    formData.append("audio_file", audioBlob, "guesstimate_articulation.webm");
  }

  const res = await apiClient.post("/api/guesstimate/submit", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function getGuesstimateSession(sessionId: number): Promise<GuesstimateSessionResponse> {
  const res = await apiClient.get<GuesstimateSessionResponse>(`/api/guesstimate/session/${sessionId}`);
  return res.data;
}

export async function getGuesstimateReport(sessionId: number): Promise<GuesstimateSessionResponse> {
  const res = await apiClient.get<GuesstimateSessionResponse>(`/api/guesstimate/report/${sessionId}`);
  return res.data;
}
