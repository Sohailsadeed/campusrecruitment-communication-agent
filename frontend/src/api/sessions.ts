import { apiClient } from "./client";
import type { SessionDetail, SessionSummary } from "../types";

export async function listSessions(): Promise<SessionSummary[]> {
  const { data } = await apiClient.get<SessionSummary[]>("/api/sessions");
  return data;
}

export async function getSession(id: number): Promise<SessionDetail> {
  const { data } = await apiClient.get<SessionDetail>(`/api/sessions/${id}`);
  return data;
}

export async function deleteSession(id: number): Promise<void> {
  await apiClient.delete(`/api/sessions/${id}`);
}

export interface UploadSessionInput {
  title: string;
  description?: string;
  durationSeconds: number;
  roundType?: string;
  roundMetadata?: Record<string, any>;
  videoBlob?: Blob;
  audioBlob?: Blob;
}

export async function uploadSession(
  input: UploadSessionInput
): Promise<SessionSummary> {
  const form = new FormData();
  form.append("title", input.title);
  if (input.description) form.append("description", input.description);
  form.append("duration_seconds", String(input.durationSeconds));
  form.append("round_type", input.roundType || "jam");
  if (input.roundMetadata) {
    form.append("round_metadata", JSON.stringify(input.roundMetadata));
  }
  if (input.videoBlob) {
    form.append("video", input.videoBlob, "recording.webm");
  }
  if (input.audioBlob) {
    form.append("audio", input.audioBlob, "recording.webm");
  }
  const { data } = await apiClient.post<SessionSummary>(
    "/api/sessions",
    form
  );
  return data;
}
