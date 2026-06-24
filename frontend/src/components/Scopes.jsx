import { useEffect, useState } from "react";
import { api } from "../api.js";
import RelatedPanel from "./RelatedPanel.jsx";

export default function Scopes({ onNavigate, nav, onNavConsumed }) {
  const [scopes, setScopes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setScopes(await api.listScopes());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  // Consume a cross-tab navigation request: open the targeted scope's drawer.
  useEffect(() => {
    if (!nav || loading) return;
    const s = scopes.find((x) => x.id === nav.id);
    if (s) setSelected(s);
    onNavConsumed?.();
  }, [nav, loading, scopes]);

  return (
    <div className="sched">
      <div className="sched-toolbar">
        <span className="count">{scopes.length} scopes</span>
        <div className="spacer" />
        <button
          className="btn"
          onClick={() => setSelected({ __new: true, title: "", unique_test_reference: "" })}
        >
          + Add scope
        </button>
      </div>
      <div className="sched-main">
        <div className="list section-pad">
          {loading ? (
            <div className="loading">Loading scopes…</div>
          ) : error ? (
            <div className="empty">{error}</div>
          ) : scopes.length === 0 ? (
            <div className="empty">No scopes yet. Use “Add scope”.</div>
          ) : (
            scopes.map((s) => (
              <div key={s.id} className="cardrow" onClick={() => setSelected(s)}>
                <h3>{s.title}</h3>
                <div className="meta">
                  {s.unique_test_reference && <span className="badge">{s.unique_test_reference}</span>}
                  <span>{(s.attachments || []).length} file(s)</span>
                </div>
              </div>
            ))
          )}
        </div>
        {selected && (
          <ScopeDrawer
            key={selected.id || "new"}
            scope={selected}
            onNavigate={onNavigate}
            onClose={() => setSelected(null)}
            onSaved={() => { setSelected(null); load(); }}
            onDeleted={() => { setSelected(null); load(); }}
          />
        )}
      </div>
    </div>
  );
}

function ScopeDrawer({ scope, onNavigate, onClose, onSaved, onDeleted }) {
  const isNew = !!scope.__new;
  const [form, setForm] = useState({
    title: scope.title || "",
    unique_test_reference: scope.unique_test_reference || "",
  });
  const [atts, setAtts] = useState(scope.attachments || []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function save() {
    if (!form.title.trim()) { setErr("Title is required"); return; }
    setBusy(true);
    setErr("");
    const body = {
      title: form.title,
      unique_test_reference: form.unique_test_reference || null,
    };
    try {
      if (isNew) await api.createScope(body);
      else await api.updateScope(scope.id, body);
      onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await api.uploadScopeAttachment(scope.id, file);
      setAtts(await api.listScopeAttachments(scope.id));
    } catch (e2) {
      setErr(e2.message);
    }
  }

  async function removeAtt(id) {
    try {
      await api.deleteScopeAttachment(id);
      setAtts(await api.listScopeAttachments(scope.id));
    } catch (e2) {
      setErr(e2.message);
    }
  }

  async function del() {
    if (!window.confirm("Delete this scope and its files?")) return;
    try {
      await api.deleteScope(scope.id);
      onDeleted();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <aside className="drawer">
      <div className="dh">
        <button className="closeX" onClick={onClose}>×</button>
        <div className="vt">{isNew ? "New scope" : form.title || "Scope"}</div>
        <div className="muted" style={{ fontSize: 12 }}>Scoping document</div>
      </div>
      <div className="body">
        <div className="field">
          <label>Title</label>
          <input className="in" value={form.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="field">
          <label>Unique test reference</label>
          <input
            className="in"
            value={form.unique_test_reference}
            onChange={(e) => set("unique_test_reference", e.target.value)}
            placeholder="links to a test / booking by this key"
          />
        </div>

        {!isNew ? (
          <div className="field">
            <label>Attachments</label>
            {atts.map((a) => (
              <div className="att" key={a.id}>
                <span className="ic">▣</span>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    api.downloadScopeAttachment(a.id, a.filename).catch((err) => setErr(err.message));
                  }}
                >
                  {a.filename}
                </a>
                <button className="att-remove" title="Remove attachment" onClick={() => removeAtt(a.id)}>×</button>
              </div>
            ))}
            <label className="btn ghost" style={{ width: "100%", marginTop: 4, display: "block", textAlign: "center" }}>
              Upload file
              <input type="file" style={{ display: "none" }} onChange={upload} />
            </label>
          </div>
        ) : (
          <p className="muted" style={{ fontSize: 11 }}>Save the scope first, then add files.</p>
        )}

        <RelatedPanel
          reference={form.unique_test_reference}
          self={{ type: "scope", id: scope.id }}
          onNavigate={onNavigate}
        />

        {err && <p className="err">{err}</p>}
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={save}>
          {busy ? "Saving…" : isNew ? "Create scope" : "Save changes"}
        </button>
        {!isNew && (
          <button className="btn ghost" style={{ width: "100%", marginTop: 8 }} onClick={del}>
            Delete scope
          </button>
        )}
      </div>
    </aside>
  );
}
