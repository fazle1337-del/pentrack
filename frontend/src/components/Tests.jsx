import { useEffect, useState } from "react";
import { api } from "../api.js";
import { ratingBg, statusDot, TEST_STATUSES } from "../constants.js";

const BAU_OPTS = ["BAU", "Project"];

export default function Tests({ teams, users }) {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openTest, setOpenTest] = useState(null);

  async function load() {
    setLoading(true);
    try {
      setTests(await api.listTests());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  if (loading) return <div className="loading">Loading tests…</div>;
  if (error) return <div className="empty">{error}</div>;

  return (
    <div className="wrap">
      <div className="list section-pad">
        {tests.length === 0 && <div className="empty">No tests yet. Import a CSV to create one.</div>}
        {tests.map((t) => (
          <div key={t.id} className="cardrow" onClick={() => setOpenTest(t)}>
            <h3>{t.name}</h3>
            <div className="meta">
              <span className="badge">{t.bau_or_project || "—"}</span>
              <span className="badge">{t.status}</span>
              {t.penetration_tester && <span> · {t.penetration_tester}</span>}
              {t.unique_test_reference && <span className="badge">{t.unique_test_reference}</span>}
              {t.date_logged && <span> · logged {t.date_logged}</span>}
            </div>
          </div>
        ))}
      </div>

      {openTest && (
        <TestDrawer
          key={openTest.id}
          test={openTest}
          onClose={() => setOpenTest(null)}
          onSaved={(updated) => {
            setTests((list) => list.map((x) => (x.id === updated.id ? updated : x)));
            setOpenTest(updated);
          }}
        />
      )}
    </div>
  );
}

function TestDrawer({ test, onClose, onSaved }) {
  const [form, setForm] = useState({ ...test });
  const [findings, setFindings] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.listFindings(test.id).then(setFindings).catch(() => {});
  }, [test.id]);

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function save() {
    setBusy(true);
    setErr("");
    try {
      const updated = await api.updateTest(test.id, {
        name: form.name,
        penetration_tester: form.penetration_tester,
        unique_test_reference: form.unique_test_reference,
        tester_reference: form.tester_reference,
        scope: form.scope,
        bau_or_project: form.bau_or_project || null,
        itsm_reference: form.itsm_reference,
        status: form.status,
        date_logged: form.date_logged || null,
        due_date: form.due_date || null,
        scheduled_date: form.scheduled_date || null,
      });
      onSaved(updated);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="drawer">
      <div className="dh">
        <button className="closeX" onClick={onClose}>
          ×
        </button>
        <div className="vt">{form.name || "Untitled test"}</div>
        <div className="muted" style={{ fontSize: 12 }}>Edit test details</div>
      </div>
      <div className="body">
        <div className="field">
          <label>Test name</label>
          <input className="in" value={form.name || ""} onChange={(e) => set("name", e.target.value)} />
        </div>
        <div className="row2">
          <div className="field">
            <label>Penetration tester</label>
            <input className="in" value={form.penetration_tester || ""} onChange={(e) => set("penetration_tester", e.target.value)} />
          </div>
          <div className="field">
            <label>Unique test reference</label>
            <input className="in" value={form.unique_test_reference || ""} onChange={(e) => set("unique_test_reference", e.target.value)} />
          </div>
        </div>
        <div className="row2">
          <div className="field">
            <label>BAU / Project</label>
            <select value={form.bau_or_project || ""} onChange={(e) => set("bau_or_project", e.target.value)}>
              <option value="">—</option>
              {BAU_OPTS.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Status</label>
            <select value={form.status} onChange={(e) => set("status", e.target.value)}>
              {TEST_STATUSES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Scope</label>
          <textarea value={form.scope || ""} onChange={(e) => set("scope", e.target.value)} />
        </div>
        <div className="row2">
          <div className="field">
            <label>Date logged</label>
            <input className="in" type="date" value={form.date_logged || ""} onChange={(e) => set("date_logged", e.target.value)} />
          </div>
          <div className="field">
            <label>Scheduled date</label>
            <input className="in" type="date" value={form.scheduled_date || ""} onChange={(e) => set("scheduled_date", e.target.value)} />
          </div>
        </div>
        {err && <p className="err">{err}</p>}
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={save}>
          {busy ? "Saving…" : "Save test"}
        </button>

        <h4 style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", marginTop: 22 }}>
          Findings in this test ({findings.length})
        </h4>
        {findings.length === 0 ? (
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
  );
}
