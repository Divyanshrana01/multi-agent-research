import { useState } from "react";
import { useApiKey } from "../context/ApiKeyContext";
import { useTheme } from "../context/ThemeContext";
import { useHealth, useStats } from "../api/hooks";
import { Button, Panel, PanelBody, PanelHead, TextField } from "../components/ui";
import styles from "./Settings.module.css";

export default function Settings() {
  const { hasKey, save, clear } = useApiKey();
  const { theme, toggle } = useTheme();
  const health = useHealth();
  const stats = useStats();
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Settings</h1>
      </header>

      <Panel>
        <PanelHead>Access</PanelHead>
        <PanelBody>
          <div className={styles.stack}>
            <TextField
              label="API key"
              type="password"
              value={draft}
              placeholder={hasKey ? "•••••••• saved" : "X-API-Key"}
              hint="Sent as the X-API-Key header. Stored in this browser only, never sent anywhere else."
              autoComplete="off"
              onChange={(e) => {
                setDraft(e.target.value);
                setSaved(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && draft.trim()) {
                  save(draft);
                  setDraft("");
                  setSaved(true);
                }
              }}
            />
            <div className={styles.row}>
              <Button
                variant="primary"
                disabled={!draft.trim()}
                onClick={() => {
                  save(draft);
                  setDraft("");
                  setSaved(true);
                }}
              >
                Save key
              </Button>
              <Button
                disabled={!hasKey}
                onClick={() => {
                  clear();
                  setSaved(false);
                }}
              >
                Clear saved key
              </Button>
              {saved && <span className={styles.ok}>Saved</span>}
            </div>
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHead>Appearance</PanelHead>
        <PanelBody>
          <div className={styles.row}>
            <span className={styles.label}>
              Currently using the {theme} theme.
            </span>
            <Button onClick={toggle}>Switch to {theme === "dark" ? "light" : "dark"}</Button>
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHead>Service</PanelHead>
        <PanelBody>
          <dl className={styles.facts}>
            <Fact label="Overall" value={health.data?.status} />
            <Fact label="Redis" value={health.data?.redis} />
            <Fact label="Database" value={health.data?.database} />
            <Fact label="Cached answers" value={stats.data?.redis.cache_entries} />
            <Fact label="Active sessions" value={stats.data?.redis.active_sessions} />
            <Fact
              label="Redis uptime"
              value={stats.data ? `${stats.data.redis.uptime_hours} h` : undefined}
            />
            <Fact label="Gateway" value={stats.data?.tensorzero_url} />
            <Fact label="Guardrail" value={stats.data?.guardrail_id || "not configured"} />
          </dl>
          {stats.error && (
            <p className={styles.hint}>
              Stats need a valid API key — add one above to see them.
            </p>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}

function Fact({ label, value }: { label: string; value?: string | number }) {
  return (
    <div className={styles.fact}>
      <dt>{label}</dt>
      <dd data-state={value === "ok" ? "ok" : value === "error" ? "error" : undefined}>
        {value ?? "—"}
      </dd>
    </div>
  );
}
