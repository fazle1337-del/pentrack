import { useEffect, useState } from "react";
import { api } from "../api.js";
import { ratingBg, statusDot, ENGAGEMENT_STATUSES } from "../constants.js";
import RelatedPanel from "./RelatedPanel.jsx";

const BAU_OPTS = ["BAU", "Project"];

export default function Tests({ teams, users, isAdmin, onNavigate, nav, onNavConsumed }) {
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

  // Consume a cross-tab navigation request: open the targeted test's drawer.
  useEffect(() => {
    if (!nav || loading) return;
    const t = tests.find((x) => x.id === nav.id);
    if (t) setOpenTest(t);
    onNavConsumed?.();
  }, [nav, loading, tests]);

  async function removeTest(t, e) {
    e.stopPropagation();
    let n = 0;
    try {
      n = (await api.listFindings(t.id)).length;
    } catch {}
    const extra = n ? ` and its ${n} finding${n === 1 ? "" : "s"}` : "";
    if (!window.confirm(`Delete test “${t.name}”${extra}? This cannot be undone.`)) return;
    try {
      await api.deleteTest(t.id);
      setTests((list) => list.filter((x) => x.id !== t.id));
      if (openTest?.id === t.id) setOpenTest(null);
    } catch (e2) {
      setError(e2.message);
    }
  }

  if (loading) return <div className="loading">Loading tests…</div>;
  if (error) return <div className="empty">{error}</div>;

  return (
    <div className="wrap">
      <div className="list section-pad">
        {tests.length === 0 && <div className="empty">No tests yet. Import a CSV to create one.</div>}
        {tests.map((t) => (
          <div key={t.id} className="cardrow" onClick={() => setOpenTest(t)}>
            {isAdmin && (
              <button
                className="row-del"
                title="Delete test"
                onClick={(e) => removeTest(t, e)}
              >
                🗑
              </button>
            )}
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
          isAdmin={isAdmin}
          onNavigate={onNavigate}
          onClose={() => setOpenTest(null)}
          onSaved={(updated) => {
            setTests((list) => list.map((x) => (x.id === updated.id ? updated : x)));
            setOpenTest(updated);
          }}
          onDeleted={(id) => {
            setTests((list) => list.filter((x) => x.id !== id));
            setOpenTest(null);
          }}
        />
      )}
    </div>
  );
}

function TestDrawer({ test, isAdmin, onNavigate, onClose, onSaved, onDeleted }) {
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

  async function del() {
    const extra = findings.length
      ? ` and its ${findings.length} finding${findings.length === 1 ? "" : "s"}`
      : "";
    if (!window.confirm(`Delete test “${form.name}”${extra}? This cannot be undone.`)) return;
    setBusy(true);
    setErr("");
    try {
      await api.deleteTest(test.id);
      onDeleted?.(test.id);
    } catch (e) {
      setErr(e.message);
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
              {ENGAGEMENT_STATUSES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
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
        <RelatedPanel
          reference={form.unique_test_reference}
          self={{ type: "test", id: test.id }}
          onNavigate={onNavigate}
        />
        {err && <p className="err">{err}</p>}
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={save}>
          {busy ? "Saving…" : "Save test"}
        </button>
        {isAdmin && (
          <button className="btn danger" style={{ width: "100%", marginTop: 8 }} disabled={busy} onClick={del}>
            Delete test
          </button>
        )}

        <h4 style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", marginTop: 22 }}>
          Findings in this test ({findings.length})
        </h4>
        {findings.length === 0 ? (
          <div className="muted">No findings linked.</div>
        ) : (
          findings.map((f) => (
            <div
              className="att"
              key={f.id}
              style={{ justifyContent: "space-between", cursor: "pointer" }}
              onClick={() => onNavigate?.("finding", f.id)}
              title="Open finding"
            >
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
