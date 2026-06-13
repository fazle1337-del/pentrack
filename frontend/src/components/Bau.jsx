import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

// High-level 18-month plan view. Each BAU test with a scheduled_date gets a
// marker positioned along an 18-month track starting this month.
export default function Bau() {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listTests()
      .then(setTests)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const start = useMemo(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  }, []);
  const MONTHS = 18;

  const months = useMemo(() => {
    const out = [];
    for (let i = 0; i < MONTHS; i += 3) {
      const d = new Date(start);
      d.setMonth(d.getMonth() + i);
      out.push(d.toLocaleString("en-GB", { month: "short", year: "2-digit" }));
    }
    return out;
  }, [start]);

  function offsetPct(dateStr) {
    const d = new Date(dateStr);
    const months =
      (d.getFullYear() - start.getFullYear()) * 12 + (d.getMonth() - start.getMonth());
    return Math.max(0, Math.min(100, (months / MONTHS) * 100));
  }

  const scheduled = tests
    .filter((t) => t.scheduled_date)
    .sort((a, b) => a.scheduled_date.localeCompare(b.scheduled_date));

  if (loading) return <div className="loading">Loading schedule…</div>;
  if (error) return <div className="empty">{error}</div>;

  return (
    <div className="timeline">
      <div className="tl-months">
        {months.map((m) => (
          <span key={m}>{m}</span>
        ))}
      </div>
      {scheduled.length === 0 ? (
        <div className="empty">No scheduled tests in the planning window.</div>
      ) : (
        scheduled.map((t) => (
          <div className="tl-row" key={t.id}>
            <div className="tl-label" title={t.name}>
              {t.name}
            </div>
            <div className="tl-track">
              <div
                className="tl-marker"
                style={{ left: `calc(${offsetPct(t.scheduled_date)}% - 3px)`, width: 10 }}
                title={`${t.name} · ${t.scheduled_date}`}
              />
            </div>
          </div>
        ))
      )}
    </div>
  );
}
