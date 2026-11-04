import { apiClient } from "./client";
import type { VocalDelivery } from "../types";

export interface StarBreakdown {
  situation: boolean;
  task: boolean;
  action: boolean;
  result: boolean;
  structure_feedback: string;
}

export interface SentenceAnalysisItem {
  index: number;
  text: string;
  start?: number | null;
  end?: number | null;
  is_conclusion_checkpoint?: boolean;
  is_rambling?: boolean;
  highlight?: "green" | "red" | "none";
  rationale?: string;
}

export interface QuestionItem {
  id: string;
  text: string;
  type: string;
  answer?: string;
  score?: number;
  feedback?: string;
  /** Set while the answer waits for the deferred transcription/emotion pass. */
  processing?: "pending" | "done" | "failed";
  processing_error?: string | null;
  // Student Communication Enhancements
  conciseness_score?: number;
  rambling_detected?: boolean;
  rambling_critique?: string;
  jargon_vs_understanding?: "textbook_rote" | "balanced" | "applied_intuition" | string;
  applied_understanding_score?: number;
  jargon_critique?: string;
  star_breakdown?: StarBreakdown;
  ideal_concise_script?: string;
  conclusion_checkpoint_index?: number | null;
  sentences?: SentenceAnalysisItem[];
  audio_url?: string;
}

export interface StartTechnicalRequest {
  role: string;
  target_company?: string;
  company_tier?: string;
  max_questions?: number;
}

export interface StartTechnicalResponse {
  session_id: number;
  role: string;
  target_company?: string;
  company_tier?: string;
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
  vocal_delivery?: VocalDelivery;
}

export interface SubmitAnswerResponse {
  session_id: number;
  /** Always null now: an answer is queued when it is submitted and scored once, at the end of the round. */
  evaluation: QuestionEvaluation | null;
  /** Always null: the answer route stores and acknowledges, and the process pass asks the next question. */
  next_question: QuestionItem | null;
  is_complete: boolean;
  /** Null until `evaluateTechnicalRound` has run for this session. */
  report?: TechnicalReportSummary | null;
  question_count: number;
  max_questions: number;
  audio_url?: string | null;
  vocal_delivery?: Record<string, unknown>;
}

/**
 * The deferred recording analysis: transcription and vocal delivery for the stored answers.
 *
 * Nothing here is a background task the server can lose. The answer is stored with `processing: "pending"`
 * and this call clears it, so a page reload or a server restart only means calling it again. It never
 * carries the next question: that is `requestTechnicalQuestion`, which does not wait on Whisper.
 */
export interface ProcessRoundResponse {
  session_id: number;
  next_question: QuestionItem | null;
  question_count: number;
  max_questions: number;
  is_complete: boolean;
  /** "done" every answer analysed · "retry" one failed or is still owed · "running" another call holds it. */
  processing: "done" | "retry" | "running";
  errors: string[];
  unprocessed: number[];
}

export interface QuestionTurnResponse {
  session_id: number;
  next_question: QuestionItem | null;
  question_count: number;
  max_questions: number;
  is_complete: boolean;
}

export interface QuestionEvaluation {
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
}

export interface RoundEvaluationResponse {
  session_id: number;
  report: TechnicalReportSummary;
  overall_score: number;
  questions: QuestionItem[];
  question_count: number;
  max_questions: number;
  is_complete: boolean;
}

export interface TechnicalReportResponse {
  session_id: number;
  role: string;
  target_company?: string;
  company_tier?: string;
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

export async function submitTechnicalAnswer(
  sessionId: number,
  answer: string,
  audioBlob?: Blob | null,
  questionRef?: string | null
): Promise<SubmitAnswerResponse> {
  const formData = new FormData();
  formData.append("session_id", String(sessionId));
  formData.append("answer", answer);
  if (questionRef) {
    formData.append("question_ref", questionRef);
  }
  if (audioBlob) {
    formData.append("audio_file", audioBlob, "articulation.webm");
  }

  const res = await apiClient.post<SubmitAnswerResponse>("/api/technical/answer", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

/**
 * Do the work the answer route deferred: transcription and vocal delivery for the queued answers.
 *
 * Nothing here is a background task the server can lose. The answer is stored with `processing: "pending"`
 * and this call clears it, so a page reload or a server restart only means calling it again. It does not
 * carry the next question -- that is `requestTechnicalQuestion`, which never waits on this pass.
 */
export async function processTechnicalRound(sessionId: number): Promise<ProcessRoundResponse> {
  const res = await apiClient.post<ProcessRoundResponse>(`/api/technical/process/${sessionId}`);
  return res.data;
}

/**
 * Ask for the question to answer next.
 *
 * The fast half of the split submission: it makes the existing question generator call and nothing else, so
 * the studio shows the next question while the previous recording is still being transcribed. A question
 * already open is returned as-is, which makes this safe to repeat after a reload or a restart.
 */
export async function requestTechnicalQuestion(sessionId: number): Promise<QuestionTurnResponse> {
  const res = await apiClient.post<QuestionTurnResponse>(`/api/technical/question/${sessionId}`);
  return res.data;
}

/**
 * Score the whole round in one pass, after every answer has been processed.
 *
 * The 503 this returns — for an unavailable model as well as for an answer whose processing has not
 * cleared — is the retryable case: the answers are saved and the session stays open, so the caller shows a
 * retry rather than a finished interview.
 */
export async function evaluateTechnicalRound(sessionId: number): Promise<RoundEvaluationResponse> {
  const res = await apiClient.post<RoundEvaluationResponse>(`/api/technical/evaluate/${sessionId}`);
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
