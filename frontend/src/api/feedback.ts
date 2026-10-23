import { apiClient } from "./client";
import type { AIFeedback } from "../types";

export async function getFeedback(sessionId: number): Promise<AIFeedback[]> {
  const { data } = await apiClient.get<AIFeedback[]>(
    `/api/sessions/${sessionId}/feedback`
  );
  return data;
}
