import { Link } from "react-router";
import type { ReportSummary, Source } from "../../api/types";
import styles from "./ReportCard.module.css";

const SOURCE_LABEL: Record<Source, string> = {
  pipeline: "Four agents ran",
  cache: "Reused from cache",
  ltm: "Reused from memory",
};

export default function ReportCard({ report }: { report: ReportSummary }) {
  const created = new Date(report.created_at);

  return (
    <article className={styles.card}>
      <h3 className={styles.topic}>
        {/* the whole card is clickable via ::after, but only the title is in the
            tab order — one stop per card, not three */}
        <Link to={`/reports/${report.id}`} className={styles.link}>
          {report.topic}
        </Link>
      </h3>

      <p className={styles.preview}>{report.preview}</p>

      <footer className={styles.meta}>
        <time dateTime={report.created_at}>
          {created.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
        </time>
        <span>{report.word_count.toLocaleString()} words</span>
        <span className={styles.source} data-source={report.source}>
          {SOURCE_LABEL[report.source]}
        </span>
      </footer>
    </article>
  );
}
