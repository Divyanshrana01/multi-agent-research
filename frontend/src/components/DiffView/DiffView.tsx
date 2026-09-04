import styles from "./DiffView.module.css";

function lineKind(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "file";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "same";
}

export default function DiffView({ text }: { text: string }) {
  return (
    <div className={styles.diff}>
      {text.split("\n").map((line, i) => (
        // eslint-disable-next-line react/no-array-index-key -- diff lines have no id, and the list never reorders
        <div key={i} className={styles.line} data-kind={lineKind(line)}>
          {line || " "}
        </div>
      ))}
    </div>
  );
}
