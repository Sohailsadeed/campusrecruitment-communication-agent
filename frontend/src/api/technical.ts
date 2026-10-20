import { apiClient } from "./client";

export interface QuestionItem {
  id: string;
  text: string;
  type: string;
  answer?: string;
  score?: number;
  feedback?: string;
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

export interface SubmitAnswerResponse {
  session_id: number;
  evaluation: {
    score: number;
    feedback: string;
  };
  next_question?: QuestionItem;
  is_complete: boolean;
  report?: {
    total_score: number;
    strengths: string[];
    weaknesses: string[];
    summary: string;
  };
  question_count: number;
  max_questions: number;
}

export interface TechnicalReportResponse {
  session_id: number;
  role: string;
  target_company?: string;
  overall_score: number;
  report: {
    total_score: number;
    strengths: string[];
    weaknesses: string[];
    summary: string;
  };
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
