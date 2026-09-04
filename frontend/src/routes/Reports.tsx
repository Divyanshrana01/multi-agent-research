import { useState } from "react";
import { Link } from "react-router";
import { useReports } from "../api/hooks";
import ReportCard from "../components/ReportCard/ReportCard";
import { Button, Empty, Skeleton } from "../components/ui";
import styles from "./Reports.module.css";

export default function Reports() {
  // one cursor, not infinite scroll: the back button should return you to the
  // page you were on, and infinite lists lose that
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const { data, isPending, error } = useReports(cursor);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Reports</h1>
        <p className={styles.sub}>
          The most recent report for each topic you&apos;ve researched.
        </p>
      </header>

      {isPending && (
        <div className={styles.grid}>
          {Array.from({ length: 6 }, (_, i) => (
            <div className={styles.skeletonCard} key={i}>
              <Skeleton height={18} width="70%" />
              <Skeleton height={13} />
              <Skeleton height={13} width="85%" />
            </div>
          ))}
        </div>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error.message}
        </p>
      )}

      {data && data.reports.length === 0 && (
        <Empty title="No reports yet">
          Run your first topic on the <Link to="/">Run</Link> page and it will appear here.
        </Empty>
      )}

      {data && data.reports.length > 0 && (
        <>
          <div className={styles.grid}>
            {data.reports.map((report) => (
              <ReportCard report={report} key={report.id} />
            ))}
          </div>

          <div className={styles.pager}>
            <Button
              disabled={history.length === 0}
              onClick={() => {
                const previous = history[history.length - 1] ?? null;
                setHistory((h) => h.slice(0, -1));
                setCursor(previous);
              }}
            >
              Newer
            </Button>
            <Button
              disabled={!data.next_cursor}
              onClick={() => {
                if (!data.next_cursor) return;
                setHistory((h) => [...h, cursor ?? ""]);
                setCursor(data.next_cursor);
              }}
            >
              Older
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
