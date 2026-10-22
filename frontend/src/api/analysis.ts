import { apiClient } from "./client";
import type {
  ProgressMetric,
  ProgressSummary,
  SessionAnalysis,
  SessionDetail,
} from "../types";

export async function analyzeSession(id: number): Promise<SessionDetail> {
  const { data } = await apiClient.post<SessionDetail>(
    `/api/sessions/${id}/analyze`
  );
  return data;
}

export async function getAnalysis(id: number): Promise<SessionAnalysis> {
  const { data } = await apiClient.get<SessionAnalysis>(
    `/api/sessions/${id}/analysis`
  );
  return data;
}

export async function getProgressSummary(): Promise<ProgressSummary> {
  const { data } = await apiClient.get<ProgressSummary>(
    "/api/progress/summary"
  );
  return data;
}

export async function getProgressMetrics(): Promise<ProgressMetric[]> {
  const { data } = await apiClient.get<ProgressMetric[]>(
    "/api/progress/metrics"
  );
  return data;
}

export interface TechnicalTimelinePoint {
  session_id: number;
  title: string;
  role: string;
  target_company?: string | null;
  score: number;
  conciseness_score?: number | null;
  rambling_rate?: number | null;
  applied_understanding_score?: number | null;
  rote_reliance_score?: number | null;
  benchmark: number;
  competitive_threshold: number;
  questions_count: number;
  verdict: string;
  created_at: string;
}

export interface TechnicalCompetencyMetric {
  category: string;
  avg_score: number;
  challenges_count: number;
}

export interface TechnicalProgressResponse {
  timeline: TechnicalTimelinePoint[];
  summary: {
    total_drills: number;
    completed_drills: number;
    avg_score: number;
    peak_score: number;
    avg_conciseness?: number;
    avg_rambling_rate?: number;
    avg_applied_understanding?: number;
    avg_rote_reliance?: number;
    latest_verdict: string;
  };
  competencies: TechnicalCompetencyMetric[];
}

export async function getTechnicalProgress(): Promise<TechnicalProgressResponse> {
  const { data } = await apiClient.get<TechnicalProgressResponse>(
    "/api/progress/technical"
  );
  return data;
}

export interface GuesstimateTimelinePoint {
  session_id: number;
  title: string;
  category: string;
  difficulty: string;
  score: number;
  structure_score: number;
  math_score: number;
  proxy_score: number;
  sanity_score: number;
  verdict: string;
  created_at: string;
}

export interface GuesstimateCategoryMetric {
  category: string;
  avg_score: number;
  drills_count: number;
}

export interface GuesstimateProgressResponse {
  timeline: GuesstimateTimelinePoint[];
  summary: {
    total_drills: number;
    completed_drills: number;
    avg_score: number;
    peak_score: number;
    latest_verdict: string;
  };
  categories: GuesstimateCategoryMetric[];
}

export async function getGuesstimateProgress(): Promise<GuesstimateProgressResponse> {
  const { data } = await apiClient.get<GuesstimateProgressResponse>(
    "/api/progress/guesstimate"
  );
  return data;
}

export interface HRTimelinePoint {
  session_id: number;
  title: string;
  role: string;
  target_company?: string | null;
  mode: string;
  score: number;
  avg_ownership_score: number;
  avg_star_completeness: number;
  avg_specificity_score: number;
  verdict: string;
  created_at: string;
}

export interface HRCompetencyMetric {
  track: string;
  avg_score: number;
  drills_count: number;
}

export interface HRProgressResponse {
  timeline: HRTimelinePoint[];
  summary: {
    total_drills: number;
    completed_drills: number;
    avg_score: number;
    peak_score: number;
    latest_verdict: string;
  };
  competencies: HRCompetencyMetric[];
}

export async function getHRProgress(): Promise<HRProgressResponse> {
  const { data } = await apiClient.get<HRProgressResponse>(
    "/api/progress/hr"
  );
  return data;
}

export interface ReadinessCardMetric {
  label: string;
  value: string | number | null;
  unit: string;
}

export interface PlacementReadinessCard {
  key: "jam" | "technical" | "guesstimate" | "hr";
  title: string;
  track_number: string;
  attempt_count: number;
  completed_count: number;
  latest_attempt_at?: string | null;
  latest_session_id?: number | null;
  status: "ready" | "in_progress" | "not_attempted";
  primary_metric: ReadinessCardMetric;
  secondary_metrics: ReadinessCardMetric[];
  drill_path: string;
  report_path?: string | null;
}

export interface PlacementReadinessResponse {
  cards: PlacementReadinessCard[];
  attempted_count: number;
  ready_count: number;
  total_rounds: number;
  evaluation_rule: string;
}

export async function getPlacementReadiness(): Promise<PlacementReadinessResponse> {
  const { data } = await apiClient.get<PlacementReadinessResponse>(
    "/api/progress/placement-readiness"
  );
  return data;
}

