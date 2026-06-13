import { useEffect, useState } from "react";
import { api } from "../api.js";
import { ratingBg, ratingClass, statusDot, fmtDate } from "../constants.js";

export default function Tests({ teams, users }) {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openTest, setOpenTest] = useState(null);
  const [findings, setFindings] = useState([]);
  const [fLoading, setFLoading] = useState(false);

  useEffect(() => {
    api
      .listTests()
      .then(setTests)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function openFindings(t) {
    setOpenTest(t);
    setFLoading(true);
    try {
      setFindings(await api.listFindings(t.id));
    } catch (e) {
      setError(e.message);
    } finally {
      setFLoading(false);
    }
  }

  if (loading) return <div className="loading">Loading tests…</div>;
  if (error) return <div className="empty">{error}</div>;

  return (
    <div className="wrap">
      <div className="list section-pad">
        {tests.length === 0 && <div className="empty">No tests yet.</div>}
        {tests.map((t) => (
          <div key={t.id} className="cardrow" onClick={() => openFindings(t)}>
            <h3>{t.name}</h3>
            <div className="meta">
              <span className="badge">{t.bau_or_project || "—"}</span>
              <span className="badge">{t.status}</span>
              {t.penetration_tester && <span> · {t.penetration_tester}</span>}
              {t.unique_test_reference && <span className="badge">{t.unique_test_reference}</span>}
              {t.tester_reference && <span> · {t.tester_reference}</span>}
              {t.date_logged && <span> · logged {t.date_logged}</span>}
            </div>
          </div>
        ))}
      </div>

      {openTest && (
        <aside className="drawer">
          <div className="dh">
            <button className="closeX" onClick={() => setOpenTest(null)}>
              ×
            </button>
            <div className="vt">{openTest.name}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {openTest.scope || "No scope recorded"}
            </div>
          </div>
          <div className="body">
            <h4 style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em" }}>
              Findings in this test
            </h4>
            {fLoading ? (
              <div className="loading">Loading…</div>
            ) : findings.length === 0 ? (
              <div className="muted">No findings linked.</div>
            ) : (
              findings.map((f) => (
                <div className="att" key={f.id} style={{ justifyContent: "space-between" }}>
                  <span>
                    <span className={"sw " + ratingBg(f.net_rating)} style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, marginRight: 7 }} />
                    {f.vulnerability || "Untitled"}
                  </span>
                  <span className="status">
                    <span className={"d " + statusDot(f.status)} />
                    <span className="muted" style={{ fontSize: 11 }}>{f.status}</span>
                  </span>
                </div>
              ))
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
