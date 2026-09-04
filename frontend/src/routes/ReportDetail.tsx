import { Link, useParams } from "react-router";
import { useReport } from "../api/hooks";
import type { Source } from "../api/types";
import ReportBody from "../components/ReportBody/ReportBody";
import DiffView from "../components/DiffView/DiffView";
import { Chip, Panel, PanelHead, Skeleton } from "../components/ui";
import styles from "./ReportDetail.module.css";

const SOURCE_LABEL: Record<Source, string> = {
  pipeline: "Four agents ran",
  cache: "Reused from cache",
  ltm: "Reused from memory",
};

export default function ReportDetail() {
  const { id } = useParams();
  const { data, isPending, error } = useReport(id);

  // skeletons rather than a spinner: the page keeps its shape, so nothing
  // jumps when the content lands
  if (isPending) {
    return (
      <div className={styles.page}>
        <Skeleton height={30} width="55%" />
        <Skeleton height={14} width="30%" />
        <div className={styles.skeletonBody}>
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton height={14} width={i % 3 === 2 ? "78%" : "100%"} key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <p className={styles.error} role="alert">
          {error.message}
        </p>
        <Link to="/reports">Back to all reports</Link>
      </div>
    );
  }

  const created = new Date(data.created_at);

  return (
    <article className={styles.page}>
      <nav aria-label="Breadcrumb">
        <Link to="/reports" className={styles.back}>
          All reports
        </Link>
      </nav>

      <header className={styles.head}>
        <h1 className={styles.title}>{data.topic}</h1>
        <div className={styles.meta}>
          <time dateTime={data.created_at}>
            {created.toLocaleString("en-GB", {
              day: "numeric",
              month: "long",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
          <Chip>{data.word_count.toLocaleString()} words</Chip>
          <Chip>{SOURCE_LABEL[data.source]}</Chip>
        </div>
      </header>

      <Panel>
        <div className={styles.reader}>
          <ReportBody markdown={data.report} />
        </div>
      </Panel>

      {data.diff && (
        <Panel>
          <PanelHead>Changes since the previous report on this topic</PanelHead>
          <DiffView text={data.diff} />
        </Panel>
      )}
    </article>
  );
}
