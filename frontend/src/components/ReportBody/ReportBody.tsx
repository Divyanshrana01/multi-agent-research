import type { ReactNode } from "react";
import styles from "./ReportBody.module.css";

/**
 * Renders the loose markdown the writer agent actually produces — headings,
 * bullets, bold, italic — and nothing else. React builds the elements, so
 * there's no innerHTML anywhere and model output can't inject markup.
 */

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /\*\*(.+?)\*\*|\*(.+?)\*/g;
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    if (match[1] !== undefined) out.push(<strong key={key++}>{match[1]}</strong>);
    else if (match[2] !== undefined) out.push(<em key={key++}>{match[2]}</em>);
    last = match.index + match[0].length;
  }

  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function ReportBody({ markdown }: { markdown: string }) {
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  let key = 0;

  const flushList = () => {
    if (list.length) {
      blocks.push(<ul key={`ul-${key++}`}>{list}</ul>);
      list = [];
    }
  };

  for (const raw of markdown.split("\n")) {
    const line = raw.trim();

    if (!line) {
      flushList();
      continue;
    }

    const bullet = /^[-*•]\s+(.*)$/.exec(line) ?? /^\d+[.)]\s+(.*)$/.exec(line);
    if (bullet?.[1]) {
      list.push(<li key={`li-${key++}`}>{inline(bullet[1])}</li>);
      continue;
    }
    flushList();

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading?.[1] && heading[2]) {
      const body = inline(heading[2]);
      blocks.push(
        heading[1].length <= 2 ? <h2 key={`h-${key++}`}>{body}</h2> : <h3 key={`h-${key++}`}>{body}</h3>,
      );
      continue;
    }

    // "Executive Summary:" — the writer emits these without any hashes
    if (/^[A-Z][A-Za-z ]{2,40}:$/.test(line)) {
      blocks.push(<h2 key={`h-${key++}`}>{line.slice(0, -1)}</h2>);
      continue;
    }

    blocks.push(<p key={`p-${key++}`}>{inline(line)}</p>);
  }

  flushList();

  return <div className={styles.doc}>{blocks}</div>;
}
