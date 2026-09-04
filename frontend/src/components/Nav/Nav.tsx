import { NavLink } from "react-router";
import { useTheme } from "../../context/ThemeContext";
import { useApiKey } from "../../context/ApiKeyContext";
import { useHealth } from "../../api/hooks";
import styles from "./Nav.module.css";

const LINKS = [
  { to: "/", label: "Run", end: true },
  { to: "/reports", label: "Reports", end: false },
  { to: "/settings", label: "Settings", end: false },
];

export default function Nav() {
  const { theme, toggle } = useTheme();
  const { hasKey } = useApiKey();
  const { data: health } = useHealth();

  const serviceState = health?.status === "ok" ? "ok" : health ? "degraded" : "unknown";

  return (
    <header className={styles.bar}>
      <span className={styles.mark} aria-hidden="true">
        R
      </span>
      <span className={styles.name}>Research Agent</span>

      <nav className={styles.links} aria-label="Main">
        {LINKS.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            // aria-current is what a screen reader announces; the class is only
            // what sighted users see
            className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className={styles.lamps}>
        <span className={styles.lamp}>
          <span className={styles.bulb} data-state={hasKey ? "ok" : "off"} />
          {hasKey ? "Key saved" : "No key"}
        </span>
        <span className={styles.lamp} title={health ? `Redis ${health.redis}, database ${health.database}` : undefined}>
          <span className={styles.bulb} data-state={serviceState} />
          {serviceState === "ok" ? "Services up" : serviceState === "degraded" ? "Degraded" : "Checking"}
        </span>
      </div>

      <button
        type="button"
        className={styles.themeBtn}
        onClick={toggle}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      >
        {theme === "dark" ? "Light" : "Dark"}
      </button>
    </header>
  );
}
