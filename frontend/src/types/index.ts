export type SessionStatus = "pending" | "processing" | "completed" | "failed";

export interface CriticalRewrite {
  timestamp: string;
  original: string;
  polish: string;
  grade: string;
  polish_grade: string;
  tip: string;
}

export interface CompetencyVector {
  articulation: number;
  structure: number;
  technical_depth: number;
  pacing: number;
  confidence: number;
  conciseness: number;
}

export interface MasteryPoint {
  title: string;
  description: string;
}

export interface CuratedDrill {
  title: string;
  desc: string;
  duration: string;
  icon: string;
}

export interface FillerTimelineItem {
  word: string;
  timestamp_sec: number;
  timestamp_label: string;
  level: string;
}

export interface VerbalIQReport {
  total_score: number;
  verdict: string;
  feedback_content: string;
  suggestions: string[];
  rewrites?: CriticalRewrite[];
  competencies?: CompetencyVector;
  mastery_points?: MasteryPoint[];
  curated_drills?: CuratedDrill[];
  cadence_sparkline?: number[];
  filler_timeline?: FillerTimelineItem[];
  metrics?: {
    speaking_pace: number;
    filler_words_count: number;
    total_pause_time: number;
    pause_count: number;
    repetitions_count: number;
  };
}

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
  round_type?: string;
  overall_score?: number | null;
  round_metadata?: Record<string, any>;
  report?: VerbalIQReport | null;
}

export interface Transcription {
  id: number;
  session_id: number;
  text: string;
  language: string;
  confidence: number;
  created_at: string;
}

export interface JamData {
  jam_score?: number;
  jam_verdict?: string;
  hesitations_count?: number;
  repetitions_count?: number;
  repeated_words?: Record<string, number>;
  jam_infractions?: string[];
}

export interface SessionAnalysis {
  id: number;
  session_id: number;
  speaking_pace: number;
  filler_words_count: number;
  filler_words_list: Record<string, any>;
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
