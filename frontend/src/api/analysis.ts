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
