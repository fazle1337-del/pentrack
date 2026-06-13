import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Scopes() {
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

  if (loading) return <div className="loading">Loading scopes…</div>;
  if (error) return <div className="empty">{error}</div>;

  const withScope = tests.filter((t) => t.scope);

  return (
    <div className="list section-pad">
      {withScope.length === 0 ? (
        <div className="empty">No scopes recorded yet.</div>
      ) : (
        withScope.map((t) => (
          <div key={t.id} className="cardrow" style={{ cursor: "default" }}>
            <h3>{t.name}</h3>
            <div className="meta" style={{ marginBottom: 8 }}>
              <span className="badge">{t.bau_or_project || "—"}</span>
              {t.tester_reference && <span>{t.tester_reference}</span>}
            </div>
            <div className="val" style={{ whiteSpace: "pre-wrap" }}>
              {t.scope}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
