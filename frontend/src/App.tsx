import { Link, Route, Routes } from "react-router";
import Nav from "./components/Nav/Nav";
import Run from "./routes/Run";
import Reports from "./routes/Reports";
import ReportDetail from "./routes/ReportDetail";
import Settings from "./routes/Settings";
import styles from "./App.module.css";

export default function App() {
  return (
    <>
      {/* first tab stop on the page, visible only once focused */}
      <a href="#main" className={styles.skip}>
        Skip to content
      </a>

      <Nav />

      <main id="main" className={styles.main} tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Run />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/reports/:id" element={<ReportDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}

function NotFound() {
  return (
    <div className={styles.notFound}>
      <h1>No such page</h1>
      <p>
        That URL doesn&apos;t match anything here. <Link to="/">Start a new run</Link> or{" "}
        <Link to="/reports">browse past reports</Link>.
      </p>
    </div>
  );
}
