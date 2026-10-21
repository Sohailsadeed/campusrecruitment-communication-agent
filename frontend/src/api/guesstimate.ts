import { apiClient } from "./client";

export interface ModelTreeStep {
  step_name: string;
  formula_or_proxy: string;
  estimated_value: string;
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
