// Mirrors what app/main.py actually returns. Keeping these honest is the whole
// reason for choosing TypeScript here — if the backend changes shape, the build
// breaks instead of the demo.

/** Which path answered a job. Set by _process_job in app/main.py. */
export type Source = "pipeline" | "cache" | "ltm";

export type OutputFormat = "text" | "pdf" | "json";

export interface StartResponse {
  job_id: string;
  session_id: string;
}

/** /api/result/{job_id} — a union, because the fields depend on the status. */
export type JobResult =
  | { status: "pending" }
  | {
      status: "done";
      topic: string;
      report: string;
      diff: string | null;
      source: Source;
      pdf_base64?: string;
      structured?: StructuredReport;
    }
  | { status: "blocked"; error: string }
  | { status: "error"; error: string };

export interface StructuredReport {
  report_id: string;
  topic: string;
  report: string;
  created_at: string;
  word_count: number;
  checksum: string;
}

export interface ReportSummary {
  id: string;
  topic: string;
  preview: string;
  word_count: number;
  source: Source;
  created_at: string;
}

export interface ReportList {
  reports: ReportSummary[];
  next_cursor: string | null;
}

export interface ReportDetail {
  id: string;
  topic: string;
  report: string;
  word_count: number;
  source: Source;
  created_at: string;
  diff: string | null;
}

export interface SessionMessage {
  role: "user" | "assistant";
  content: string;
}

/** All four judges score 0–1. Low is good for hallucination_risk only. */
export interface Scores {
  relevance?: number;
  completeness?: number;
  hallucination_risk?: number;
  overall_quality?: number;
}

export interface Stats {
  redis: {
    total_keys: number;
    cache_entries: number;
    active_sessions: number;
    memory_used_mb: number;
    connected_clients: number;
    uptime_hours: number;
  };
  tensorzero_url: string;
  guardrail_id: string;
}

export interface Health {
  status: "ok" | "degraded";
  redis: "ok" | "error";
  database: "ok" | "error";
}
