import { apiClient } from "./client";

export interface StarBreakdown {
  situation: boolean;
  task: boolean;
  action: boolean;
  result: boolean;
  structure_feedback: string;
}

export interface QuestionItem {
  id: string;
  text: string;
  type: string;
  answer?: string;
  score?: number;
  feedback?: string;
  // Student Communication Enhancements
  conciseness_score?: number;
  rambling_detected?: boolean;
  rambling_critique?: string;
  jargon_vs_understanding?: "textbook_rote" | "balanced" | "applied_intuition" | string;
  applied_understanding_score?: number;
  jargon_critique?: string;
  star_breakdown?: StarBreakdown;
  ideal_concise_script?: string;
}

export interface StartTechnicalRequest {
  role: string;
  target_company?: string;
  max_questions?: number;
}

export interface StartTechnicalResponse {
  session_id: number;
  role: string;
  target_company?: string;
  current_question: QuestionItem;
  question_count: number;
  max_questions: number;
  is_complete: boolean;
}

export interface TechnicalReportSummary {
  total_score: number;
  avg_conciseness_score?: number;
  avg_understanding_score?: number;
  rambling_rate_percent?: number;
  strengths: string[];
  weaknesses: string[];
  summary: string;
}

export interface SubmitAnswerResponse {
  session_id: number;
  evaluation: {
    score: number;
    feedback: string;
    conciseness_score?: number;
    rambling_detected?: boolean;
    rambling_critique?: string;
    jargon_vs_understanding?: string;
    applied_understanding_score?: number;
    jargon_critique?: string;
    star_breakdown?: StarBreakdown;
    ideal_concise_script?: string;
  };
  next_question?: QuestionItem;
  is_complete: boolean;
  report?: TechnicalReportSummary;
  question_count: number;
  max_questions: number;
}

export interface TechnicalReportResponse {
  session_id: number;
  role: string;
  target_company?: string;
  overall_score: number;
  report: TechnicalReportSummary;
  questions: QuestionItem[];
  created_at?: string;
}

export async function uploadResume(file: File): Promise<{ status: string; message: string; resume_name: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await apiClient.post("/api/technical/resume/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function getResumeStatus(): Promise<{ has_resume: boolean; resume_name?: string | null }> {
  const res = await apiClient.get("/api/technical/resume/status");
  return res.data;
}

export async function clearResume(): Promise<{ status: string; message: string }> {
  const res = await apiClient.delete("/api/technical/resume");
  return res.data;
}

export async function startTechnicalInterview(data: StartTechnicalRequest): Promise<StartTechnicalResponse> {
  const res = await apiClient.post<StartTechnicalResponse>("/api/technical/start", data);
  return res.data;
}

export async function submitTechnicalAnswer(sessionId: number, answer: string): Promise<SubmitAnswerResponse> {
  const res = await apiClient.post<SubmitAnswerResponse>("/api/technical/answer", {
    session_id: sessionId,
    answer,
  });
  return res.data;
}

export async function getTechnicalSession(sessionId: number): Promise<any> {
  const res = await apiClient.get(`/api/technical/session/${sessionId}`);
  return res.data;
}

export async function getTechnicalReport(sessionId: number): Promise<TechnicalReportResponse> {
  const res = await apiClient.get<TechnicalReportResponse>(`/api/technical/report/${sessionId}`);
  return res.data;
}
