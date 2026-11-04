import { apiClient } from "./client";

/**
 * Room access exactly as the backend issues it.
 *
 * `url` comes from the server's configuration, never from a build-time constant, so moving
 * SpeakFlow to a hosted LiveKit server changes no frontend code. `token` is short-lived and
 * stays in memory for the lifetime of the connection: it is never written to localStorage and
 * never logged.
 */
export interface RoomAccess {
  url: string;
  token: string;
  room_name: string;
  identity: string;
  expires_at: string;
  ttl_seconds: number;
}

/** Ask the backend for access to the caller's own HR room for one session. */
export async function fetchHrRoomAccess(sessionId: number): Promise<RoomAccess> {
  const { data } = await apiClient.post<RoomAccess>("/api/livekit/token", {
    session_id: sessionId,
  });
  return data;
}

/** A human-readable reason for a refusal, without echoing the token or the server's internals. */
export function describeTokenError(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 401) return "Your session expired. Sign in again to join the room.";
  if (status === 404) return "This interview session is not available to you.";
  if (status === 503) return "Live audio is not configured on this server yet.";
  return "Could not reach the interview server. Check your connection and try again.";
}
