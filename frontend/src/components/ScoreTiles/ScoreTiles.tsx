import type { Scores } from "../../api/types";
import styles from "./ScoreTiles.module.css";

const META: Record<string, { label: string; higherIsBetter: boolean }> = {
  relevance: { label: "Relevance", higherIsBetter: true },
  completeness: { label: "Completeness", higherIsBetter: true },
  overall_quality: { label: "Overall quality", higherIsBetter: true },
  // the one inverted judge: 1.0 means the report is full of fabrications
  hallucination_risk: { label: "Hallucination risk", higherIsBetter: false },
};

export default function ScoreTiles({ scores }: { scores: Scores }) {
  const entries = Object.entries(scores).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number",
  );

  if (!entries.length) return null;

  return (
    <div className={styles.grid}>
      {entries.map(([key, value]) => {
        const meta = META[key] ?? { label: key, higherIsBetter: true };
        const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);

        return (
          <div className={styles.tile} key={key}>
            <div className={styles.value}>{value.toFixed(2)}</div>
            <div className={styles.name}>{meta.label}</div>
            <div className={styles.meter}>
              <i style={{ width: `${pct}%` }} data-good={meta.higherIsBetter} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
