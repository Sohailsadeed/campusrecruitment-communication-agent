import { apiClient } from "./client";
import type { VocalDelivery } from "../types";

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
  /** Set by the service, never by the model: was this answer read by one? */
  evaluator_basis?: "model" | "fallback" | "heuristic";
  evaluator_error?: string | null;
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
  speech?: AnswerSpeech;
}

export interface SpeechPauseEvent {
  after_word: string;
  before_word: string;
  at_seconds: number;
  seconds: number;
}

export interface AnswerSpeech {
  available: boolean;
  transcript_characters: number;
  words_spoken: number | null;
  speech_seconds: number | null;
  silence_seconds: number | null;
  words_per_minute: number | null;
  pace_consistency: {
    segment_rates: number[];
    spread_words_per_minute: number;
    variation_percent: number;
    continuous_speech: boolean;
  } | null;
  pauses: {
    count: number;
    average_seconds: number;
    longest_seconds: number;
    total_seconds: number;
    ordinary_count: number;
    unusual: SpeechPauseEvent[];
    micro_hesitation_count: number;
    measured: boolean;
  } | null;
  fillers: {
    count: number;
    per_100_words: number | null;
    by_phrase: Record<string, number>;
    examples: string[];
    measured_from: string;
  } | null;
  conciseness: {
    words: number | null;
    sentences: number;
    repeated_phrases: { phrase: string; occurrences: number; excerpt: string }[];
    preamble_words_before_first_personal_action: number | null;
    introduction_excerpt: string | null;
    closing_excerpt: string | null;
    conclusion_reached: boolean;
    words_per_question_word: number | null;
    rambling_signals: string[];
    rambling: boolean;
  } | null;
  observations: { metric: string; text: string; excerpt: string }[];
  unavailable: string[];
  measured_from?: string;
}

export interface SpeechRoundBlock {
  averages: Record<string, number> | null;
  answers: {
    question_number: number;
    question: string;
    available: boolean;
    words_spoken: number | null;
    words_per_minute: number | null;
    speech_seconds: number | null;
    silence_seconds: number | null;
    pace_consistency: AnswerSpeech["pace_consistency"];
    filler_count: number | null;
    fillers_per_100_words: number | null;
    pause_count: number | null;
    longest_pause_seconds: number | null;
    unusual_pause_count: number;
    rambling_signals: string[];
    repeated_phrases: { phrase: string; occurrences: number; excerpt: string }[];
    unavailable: string[];
  }[];
  observations: { question_number: number; metric: string; text: string; excerpt: string }[];
  answers_without_speech_data: number[];
}

export interface SpeechTrendsResponse {
  rounds_with_speech_data: number;
  rounds: { session_id: number; metrics: Record<string, number> }[];
  compared: {
    from_session_id: number;
    to_session_id: number;
    rounds_compared: number;
    changes: Record<string, { previous: number; latest: number; delta: number }>;
    not_compared: string[];
  } | null;
}

export interface HRReportSummary {
  total_score: number;
  avg_ownership_score: number;
  avg_star_completeness: number;
  avg_specificity_score: number;
  strengths: string[];
  weaknesses: string[];
  executive_summary: string;
  vocal_delivery?: VocalDelivery;
  speech?: SpeechRoundBlock;
  /** 'model' when a model wrote the narrative, 'empirical' when only the arithmetic did. */
  report_basis?: "model" | "empirical" | "heuristic";
  report_error?: string | null;
  answers_not_model_scored?: number;
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
  audioBlob?: Blob | null,
  questionRef?: string | null
): Promise<{
  session_id: number;
  evaluation: HRAnswerEvaluation;
  next_question?: HRQuestionItem;
  is_complete: boolean;
  report?: HRReportSummary;
  question_count: number;
  max_questions: number;
  audio_url?: string;
  speech?: AnswerSpeech;
}> {
  const formData = new FormData();
  formData.append("session_id", String(sessionId));
  formData.append("answer", answer);
  // Which question this answer is for. The server treats the round's live question as the
  // authority, so an answer typed into a tab that the voice round already moved past is refused
  // with 409 instead of being filed under the question now on screen.
  if (questionRef) {
    formData.append("question_ref", questionRef);
  }
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

export async function getHRSpeechTrends(): Promise<SpeechTrendsResponse> {
  const res = await apiClient.get<SpeechTrendsResponse>("/api/hr/speech/trends");
  return res.data;
}
