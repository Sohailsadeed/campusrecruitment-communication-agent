export type SessionStatus = "pending" | "processing" | "completed" | "failed";

export interface SessionSummary {
  id: number;
  user_id: number | null;
  title: string;
  description: string | null;
  duration_seconds: number;
  video_path: string | null;
  audio_path: string | null;
  status: SessionStatus;
  created_at: string;
}

export interface Transcription {
  id: number;
  session_id: number;
  text: string;
  language: string;
  confidence: number;
  created_at: string;
}

export interface SessionAnalysis {
  id: number;
  session_id: number;
  speaking_pace: number;
  filler_words_count: number;
  filler_words_list: Record<string, number>;
  clarity_score: number;
  eye_contact_percentage: number;
  posture_quality: number;
  created_at: string;
}

export interface AIFeedback {
  id: number;
  session_id: number;
  feedback_type: string;
  content: string;
  score: number;
  suggestions: string[];
  created_at: string;
}

export interface SessionDetail extends SessionSummary {
  transcription: Transcription | null;
  analysis: SessionAnalysis | null;
  feedback: AIFeedback[];
}

export interface ProgressSummary {
  total_sessions: number;
  completed_sessions: number;
  total_duration_seconds: number;
  avg_clarity_score: number;
  avg_speaking_pace: number;
  avg_eye_contact: number;
  avg_posture_quality: number;
  best_pace: number;
  best_clarity: number;
  total_filler_words: number;
}

export interface ProgressMetric {
  session_id: number;
  title: string;
  created_at: string;
  speaking_pace: number;
  clarity_score: number;
  filler_words_count: number;
  eye_contact_percentage: number;
  posture_quality: number;
}
