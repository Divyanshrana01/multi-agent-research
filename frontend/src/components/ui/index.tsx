import type { ButtonHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes, InputHTMLAttributes } from "react";
import { useId } from "react";
import styles from "./ui.module.css";

const cx = (...parts: (string | false | undefined)[]) => parts.filter(Boolean).join(" ");

/* ---------- panel ---------- */

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx(styles.panel, className)}>{children}</section>;
}

export function PanelHead({ children }: { children: ReactNode }) {
  return <div className={styles.panelHead}>{children}</div>;
}

export function PanelBody({ children }: { children: ReactNode }) {
  return <div className={styles.panelBody}>{children}</div>;
}

/* ---------- button ---------- */

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
  size?: "default" | "small";
  full?: boolean;
  loading?: boolean;
}

export function Button({
  variant = "ghost",
  size = "default",
  full = false,
  loading = false,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={cx(
        styles.btn,
        variant === "primary" ? styles.primary : styles.ghost,
        size === "small" && styles.small,
        full && styles.full,
      )}
      disabled={disabled ?? loading}
      {...rest}
    >
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}

/* ---------- fields ---------- */

interface FieldShellProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

/**
 * Wires label, hint and error to the control with real ids, so a screen reader
 * announces the hint and any error rather than leaving them as loose text.
 */
function FieldShell({ label, hint, error, children }: FieldShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      {children(id, describedBy)}
      {hint && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className={styles.error} id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  hint?: string;
  error?: string;
};

export function TextField({ label, hint, error, ...rest }: TextFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {(id, describedBy) => (
        <input
          id={id}
          className={styles.input}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          {...rest}
        />
      )}
    </FieldShell>
  );
}

type TextAreaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> & {
  label: string;
  hint?: string;
  error?: string;
};

export function TextArea({ label, hint, error, ...rest }: TextAreaProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {(id, describedBy) => (
        <textarea
          id={id}
          className={styles.input}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          {...rest}
        />
      )}
    </FieldShell>
  );
}

type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> & {
  label: string;
  hint?: string;
  options: { value: string; label: string }[];
};

export function SelectField({ label, hint, options, ...rest }: SelectFieldProps) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id, describedBy) => (
        <select id={id} className={styles.input} aria-describedby={describedBy} {...rest}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}

/* ---------- odds and ends ---------- */

export function Chip({ children }: { children: ReactNode }) {
  return <span className={styles.chip}>{children}</span>;
}

export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: string }) {
  return <div className={styles.skeleton} style={{ height, width }} aria-hidden="true" />;
}

/** An empty state is an invitation to act, not a shrug. */
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <strong>{title}</strong>
      {children}
    </div>
  );
}
