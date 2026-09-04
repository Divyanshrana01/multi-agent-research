import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  Health,
  JobResult,
  OutputFormat,
  ReportDetail,
  ReportList,
  Scores,
  SessionMessage,
  StartResponse,
  Stats,
} from "./types";

/**
 * Polls /api/result/{job_id} until the job leaves "pending".
 *
 * This replaces the setInterval + ref dance in the old single-file page:
 * Query stops the interval itself the moment the status changes, and a
 * finished job is never re-fetched because it can't change.
 */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<JobResult>(`/result/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 2000 : false),
    staleTime: Infinity,
    retry: 2,
  });
}

export function useStartResearch() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (body: { topic: string; output_format: OutputFormat; session_id: string }) =>
      api<StartResponse>("/research", { method: "POST", body: JSON.stringify(body) }),
    // a new run changes both of these, so refresh them rather than leaving the
    // library showing yesterday's rows
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["reports"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useReports(cursor?: string | null) {
  return useQuery({
    queryKey: ["reports", cursor ?? null],
    queryFn: () => api<ReportList>(`/reports${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`),
    staleTime: 30_000,
  });
}

export function useReport(id: string | undefined) {
  return useQuery({
    queryKey: ["report", id],
    queryFn: () => api<ReportDetail>(`/reports/${id}`),
    enabled: Boolean(id),
  });
}

export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api<{ messages: SessionMessage[] }>(`/session/${sessionId}`),
    enabled: Boolean(sessionId),
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: () => api<Stats>("/stats"),
    // the dashboard shouldn't hammer redis; a minute-old figure is fine
    staleTime: 60_000,
    retry: false,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health").catch(() => fetch("/health").then((r) => r.json() as Promise<Health>)),
    refetchInterval: 30_000,
    retry: false,
  });
}

/**
 * Scoring is a mutation, not a query: it costs four real LLM calls, so it only
 * ever runs when someone asks for it.
 */
export function useScoreReport() {
  return useMutation({
    mutationFn: (jobId: string) =>
      api<{ job_id: string; topic: string; scores: Scores }>(`/evaluate/${jobId}`),
  });
}

export function useDiff() {
  return useMutation({
    mutationFn: (topic: string) =>
      api<{ topic: string; diff: string }>(`/diff/${encodeURIComponent(topic)}`),
  });
}
