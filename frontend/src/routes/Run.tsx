import { useCallback, useEffect, useRef, useState } from "react";
import { useJob, useScoreReport, useSession, useStartResearch, useStats } from "../api/hooks";
import { pdfUrl } from "../api/client";
import type { OutputFormat, Scores } from "../api/types";
import PipelineTrack, { bannerForSource } from "../components/PipelineTrack/PipelineTrack";
import type { RunState } from "../components/PipelineTrack/PipelineTrack";
import ReportBody from "../components/ReportBody/ReportBody";
import ScoreTiles from "../components/ScoreTiles/ScoreTiles";
import DiffView from "../components/DiffView/DiffView";
import { Button, Chip, Empty, Panel, PanelBody, PanelHead, SelectField, TextArea, TextField } from "../components/ui";
import styles from "./Run.module.css";

const FORMATS = [
  { value: "text", label: "Plain text" },
  { value: "pdf", label: "PDF" },
  { value: "json", label: "Structured JSON" },
];

export default function Run() {
  const [topic, setTopic] = useState("");
  const [format, setFormat] = useState<OutputFormat>("text");
  const [sessionId, setSessionId] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState("");
  const [scores, setScores] = useState<Scores | null>(null);

  const start = useStartResearch();
  const job = useJob(jobId);
  const score = useScoreReport();
  const session = useSession(sessionId);
  const stats = useStats();

  const startedAt = useRef<number | null>(null);
  const result = job.data;
  const running = start.isPending || result?.status === "pending";

  // ticks while a job is in flight and freezes on the final figure
  useEffect(() => {
    if (!running) return;
    startedAt.current ??= Date.now();
    const id = window.setInterval(() => {
      setElapsed(`${((Date.now() - (startedAt.current ?? Date.now())) / 1000).toFixed(1)}s`);
    }, 100);
    return () => window.clearInterval(id);
  }, [running]);

  const submit = useCallback(() => {
    const trimmed = topic.trim();
    if (trimmed.length < 3) return;

    setScores(null);
    setJobId(null);
    startedAt.current = Date.now();
    setElapsed("0.0s");

    start.mutate(
      { topic: trimmed, output_format: format, session_id: sessionId },
      {
        onSuccess: (data) => {
          setJobId(data.job_id);
          setSessionId(data.session_id);
        },
      },
    );
  }, [topic, format, sessionId, start]);

  const { state, title, banner } = describeRun(running, result, start.error?.message);

  return (
    <div className={styles.grid}>
      <div className={styles.rail}>
        <Panel>
          <PanelHead>New research</PanelHead>
          <PanelBody>
            <div className={styles.form}>
              <TextArea
                label="Topic"
                value={topic}
                placeholder="Quantum computing advances in 2024"
                hint="Press ⌘↵ to start."
                onChange={(e) => setTopic(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
                }}
              />
              <SelectField
                label="Deliver as"
                value={format}
                options={FORMATS}
                onChange={(e) => setFormat(e.target.value as OutputFormat)}
              />
              <TextField
                label="Session"
                value={sessionId}
                placeholder="New session"
                hint="Reused across requests so the agents keep your earlier questions in mind."
                onChange={(e) => setSessionId(e.target.value)}
              />
              <Button
                variant="primary"
                full
                onClick={submit}
                loading={running}
                disabled={topic.trim().length < 3}
              >
                {running ? "Researching" : "Start research"}
              </Button>
            </div>
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHead>
            Redis
            <Button size="small" onClick={() => void stats.refetch()}>
              Refresh
            </Button>
          </PanelHead>
          <div className={styles.readings}>
            <Reading label="Cached answers" value={stats.data?.redis.cache_entries} />
            <Reading label="Active sessions" value={stats.data?.redis.active_sessions} />
            <Reading label="Keys in Redis" value={stats.data?.redis.total_keys} />
            <Reading label="Memory" value={stats.data?.redis.memory_used_mb} unit="MB" />
          </div>
        </Panel>
      </div>

      <div className={styles.stage}>
        <PipelineTrack state={state} title={title} elapsed={elapsed} jobId={jobId} banner={banner} />

        {result?.status === "done" && (
          <Panel>
            <PanelHead>
              <span>{result.topic}</span>
              <Chip>{countWords(result.report)} words</Chip>
            </PanelHead>

            <div className={styles.readerWrap}>
              <div className={styles.reader}>
                <ReportBody markdown={result.report} />
              </div>
              <div className={styles.readerFade} aria-hidden="true" />
            </div>

            <div className={styles.actions}>
              <Button onClick={() => jobId && window.open(pdfUrl(jobId), "_blank")}>Download PDF</Button>
              <Button
                onClick={() =>
                  jobId &&
                  score.mutate(jobId, { onSuccess: (data) => setScores(data.scores) })
                }
                loading={score.isPending}
              >
                {score.isPending ? "Scoring" : "Score this report"}
              </Button>
            </div>
          </Panel>
        )}

        {scores && (
          <Panel>
            <PanelHead>
              Judge scores
              <span className={styles.subtle}>low is good for hallucination risk</span>
            </PanelHead>
            <ScoreTiles scores={scores} />
          </Panel>
        )}

        {result?.status === "done" && result.diff && (
          <Panel>
            <PanelHead>Changes since the previous report on this topic</PanelHead>
            <DiffView text={result.diff} />
          </Panel>
        )}
      </div>

      <div className={styles.rail}>
        <Panel>
          <PanelHead>
            Session
            <Button
              size="small"
              onClick={() => {
                setSessionId("");
              }}
            >
              New session
            </Button>
          </PanelHead>
          {session.data?.messages.length ? (
            <div className={styles.turns}>
              {session.data.messages.map((message, i) => (
                // eslint-disable-next-line react/no-array-index-key -- messages have no id and only ever append
                <div className={styles.turn} key={i}>
                  <div className={styles.turnRole} data-role={message.role}>
                    {message.role === "user" ? "You" : "Agent"}
                  </div>
                  <div className={styles.turnText}>{message.content}</div>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No session yet">
              Your questions and the reports the agents return will collect here.
            </Empty>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Reading({ label, value, unit }: { label: string; value?: number; unit?: string }) {
  return (
    <div className={styles.reading}>
      <div className={styles.readingValue}>
        {value ?? "—"}
        {unit && value !== undefined && <small>{unit}</small>}
      </div>
      <div className={styles.readingKey}>{label}</div>
    </div>
  );
}

const countWords = (text: string) => text.split(/\s+/).filter(Boolean).length.toLocaleString();

/** Turns the job state into what the track should say. */
function describeRun(
  running: boolean,
  result: ReturnType<typeof useJob>["data"],
  startError?: string,
): { state: RunState; title: string; banner: ReturnType<typeof bannerForSource> } {
  if (startError) {
    return { state: "failed", title: "Could not start", banner: { kind: "failed", title: "Request rejected", body: startError } };
  }
  if (running) return { state: "working", title: "Working", banner: null };
  if (!result) return { state: "idle", title: "Idle", banner: null };

  switch (result.status) {
    case "done":
      return result.source === "pipeline"
        ? { state: "done", title: "Complete", banner: null }
        : {
            state: "reused",
            title: result.source === "cache" ? "Answered from cache" : "Answered from memory",
            banner: bannerForSource(result.source),
          };
    case "blocked":
      return {
        state: "blocked",
        title: "Blocked by guardrail",
        banner: { kind: "blocked", title: "The output guardrail blocked this report", body: result.error },
      };
    case "error":
      return {
        state: "failed",
        title: "Failed",
        banner: { kind: "failed", title: "The job did not finish", body: result.error },
      };
    default:
      return { state: "idle", title: "Idle", banner: null };
  }
}
