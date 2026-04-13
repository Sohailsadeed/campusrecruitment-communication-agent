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
