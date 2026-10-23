import { apiClient } from "./client";
import { ActivePlanResponse, GeneratePlanResponse, CurriculumPlan } from "../types/coach";

export async function getActiveCurriculumPlan(): Promise<ActivePlanResponse> {
  const res = await apiClient.get<ActivePlanResponse>("/api/coach/active-plan");
  return res.data;
}

export async function generateCurriculumPlan(payload: {
  target_role?: string;
  target_date?: string;
  force_replan?: boolean;
}): Promise<GeneratePlanResponse> {
  const res = await apiClient.post<GeneratePlanResponse>("/api/coach/generate-plan", payload);
  return res.data;
}

export async function completeCurriculumDay(payload: {
  plan_id: number;
  day_number: number;
  score_achieved?: number;
}): Promise<{ success: boolean; plan: Partial<CurriculumPlan> }> {
  const res = await apiClient.post("/api/coach/complete-day", payload);
  return res.data;
}

export async function autoSyncCurriculumDrills(): Promise<{
  synced: boolean;
  completed_day?: number;
  score_achieved?: number;
  message?: string;
}> {
  const res = await apiClient.post("/api/coach/auto-sync");
  return res.data;
}
