import { apiClient } from "./client";

export interface StarComponent {
  present: boolean;
  summary: string;
}

export interface StarStructure {
  situation: StarComponent;
  task: StarComponent;
  action: StarComponent;
  result: StarComponent;
  completeness_score: number;
  structure_critique: string;
}

export interface HRAnswerEvaluation {
  overall_score: number;
  star_structure: StarStructure;
  personal_ownership_score: number;
  ownership_critique: string;
  specificity_score: number;
  specificity_critique: string;
  relevance_score: number;
  relevance_critique: string;
  coaching_feedback: string;
  ideal_star_script: string;
}

export interface HRQuestionItem {
  id: string;
  track: string;
  text: string;
  rubric?: {
    green_flags?: string[];
    red_flags?: string[];
  };
  answer?: string;
  audio_url?: string;
  evaluation?: HRAnswerEvaluation;
}

export interface HRReportSummary {
  total_score: number;
  avg_ownership_score: number;
  avg_star_completeness: number;
  avg_specificity_score: number;
  strengths: string[];
  weaknesses: string[];
  executive_summary: string;
}

export interface HRSessionResponse {
  session_id: number;
  role: string;
  target_company?: string;
  interview_mode: string;
  current_question: HRQuestionItem | null;
  question_count: number;
  max_questions: number;
  is_complete: boolean;
  questions?: HRQuestionItem[];
  report?: HRReportSummary;
  overall_score?: number;
  created_at?: string;
}

export interface HRTrackInfo {
  id: string;
  title: string;
  icon: string;
  desc: string;
  rubric_focus: string;
}

export async function getHRTracks(): Promise<{ tracks: HRTrackInfo[] }> {
  const res = await apiClient.get<{ tracks: HRTrackInfo[] }>("/api/hr/tracks");
  return res.data;
}

export async function startHRInterview(data: {
  role: string;
  target_company?: string;
  interview_mode: string;
  max_questions: number;
}): Promise<HRSessionResponse> {
  const res = await apiClient.post<HRSessionResponse>("/api/hr/start", data);
  return res.data;
}

export async function submitHRAnswer(
  sessionId: number,
  answer: string,
  audioBlob?: Blob | null
): Promise<{
  session_id: number;
  evaluation: HRAnswerEvaluation;
  next_question?: HRQuestionItem;
  is_complete: boolean;
  report?: HRReportSummary;
  question_count: number;
  max_questions: number;
  audio_url?: string;
}> {
  const formData = new FormData();
  formData.append("session_id", String(sessionId));
  formData.append("answer", answer);
  if (audioBlob) {
    formData.append("audio_file", audioBlob, "behavioral_articulation.webm");
  }

  const res = await apiClient.post("/api/hr/answer", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function getHRSession(sessionId: number): Promise<HRSessionResponse> {
  const res = await apiClient.get<HRSessionResponse>(`/api/hr/session/${sessionId}`);
  return res.data;
}

export async function getHRReport(sessionId: number): Promise<HRSessionResponse> {
  const res = await apiClient.get<HRSessionResponse>(`/api/hr/report/${sessionId}`);
  return res.data;
}
