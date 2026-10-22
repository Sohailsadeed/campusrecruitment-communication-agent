import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteSession,
  getSession,
  listSessions,
  uploadSession,
  type UploadSessionInput,
} from "../api/sessions";
import {
  analyzeSession,
  getAnalysis,
  getGuesstimateProgress,
  getHRProgress,
  getPlacementReadiness,
  getProgressMetrics,
  getProgressSummary,
  getTechnicalProgress,
} from "../api/analysis";
import type { SessionDetail } from "../types";

export function useSessions() {
  return useQuery({
    queryKey: ["sessions"],
    queryFn: listSessions,
  });
}

export function useSessionDetail(id: number | undefined) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => getSession(id as number),
    enabled: typeof id === "number" && !Number.isNaN(id),
  });
}

export function useUploadSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UploadSessionInput) => uploadSession(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}

export function useAnalyzeSession() {
  const qc = useQueryClient();
  return useMutation<SessionDetail, Error, number>({
    mutationFn: (id: number) => analyzeSession(id),
    onSuccess: (data) => {
      qc.setQueryData(["session", data.id], data);
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["progress"] });
    },
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["progress"] });
    },
  });
}

export function useProgressSummary() {
  return useQuery({
    queryKey: ["progress", "summary"],
    queryFn: getProgressSummary,
  });
}

export function useProgressMetrics() {
  return useQuery({
    queryKey: ["progress", "metrics"],
    queryFn: getProgressMetrics,
  });
}

export function useTechnicalProgress() {
  return useQuery({
    queryKey: ["progress", "technical"],
    queryFn: getTechnicalProgress,
  });
}

export function useGuesstimateProgress() {
  return useQuery({
    queryKey: ["progress", "guesstimate"],
    queryFn: getGuesstimateProgress,
  });
}

export function useHRProgress() {
  return useQuery({
    queryKey: ["progress", "hr"],
    queryFn: getHRProgress,
  });
}

export function usePlacementReadiness() {
  return useQuery({
    queryKey: ["progress", "placement-readiness"],
    queryFn: getPlacementReadiness,
  });
}


