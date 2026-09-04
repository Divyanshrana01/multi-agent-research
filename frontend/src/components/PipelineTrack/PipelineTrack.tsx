import type { Source } from "../../api/types";
import styles from "./PipelineTrack.module.css";

export type RunState = "idle" | "working" | "done" | "reused" | "blocked" | "failed";

const STAGES = [
  { name: "Search", note: "gathers facts" },
  { name: "Summarise", note: "condenses them" },
  { name: "Write", note: "drafts the report" },
  { name: "Verify", note: "critic, retries on fail" },
];

interface Banner {
  kind: "reused" | "blocked" | "failed";
  title: string;
  body: string;
}

interface Props {
  state: RunState;
  title: string;
  elapsed?: string;
  jobId?: string | null;
  banner?: Banner | null;
}

export function bannerForSource(source: Source): Banner | null {
  if (source === "pipeline") return null;
  return {
    kind: "reused",
    title: source === "cache" ? "Reused a cached answer" : "Reused a stored report",
    body: "No agents ran for this request, so it cost nothing in model calls.",
  };
}

export default function PipelineTrack({ state, title, elapsed, jobId, banner }: Props) {
  // blocked and failed both leave the track unlit — nothing completed
  const trackState = state === "blocked" || state === "failed" ? "idle" : state;

  return (
    <section className={styles.run}>
      <div className={styles.head}>
        <div className={styles.state}>
          <span className={styles.orb} data-state={state} />
          {/* the one live region on the page: run state is announced, not just animated */}
          <span className={styles.title} aria-live="polite">
            {title}
          </span>
        </div>
        <div className={styles.meta}>
          {elapsed && <span>{elapsed}</span>}
          {jobId && <span className={styles.jobId}>{jobId.slice(0, 8)}</span>}
        </div>
      </div>

      <div className={styles.track} data-state={trackState}>
        <div className={styles.rail}>
          <i />
        </div>
        <ol className={styles.nodes}>
          {STAGES.map((stage) => (
            <li className={styles.node} key={stage.name}>
              <span className={styles.dot} aria-hidden="true" />
              <span className={styles.nodeName}>{stage.name}</span>
              <span className={styles.nodeNote}>{stage.note}</span>
            </li>
          ))}
        </ol>
      </div>

      {banner && (
        <div className={styles.banner} data-kind={banner.kind}>
          <span className={styles.bannerBar} aria-hidden="true" />
          <div>
            <div className={styles.bannerTitle}>{banner.title}</div>
            <div className={styles.bannerBody}>{banner.body}</div>
          </div>
        </div>
      )}
    </section>
  );
}
