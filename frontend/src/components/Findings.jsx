import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import ImportModal from "./ImportModal.jsx";
import {
  NET_RATINGS,
  FINDING_STATUSES,
  LIKELIHOOD_IMPACT,
  ratingClass,
  ratingBg,
  statusDot,
  fmtDate,
} from "../constants.js";

const SLA_OPTS = ["In", "Out"];

export default function Findings({ teams, users }) {
  const [findings, setFindings] = useState([]);
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [showImport, setShowImport] = useState(false);

  const [search, setSearch] = useState("");
  const [fRating, setFRating] = useState(new Set());
  const [fStatus, setFStatus] = useState(new Set());
  const [fSla, setFSla] = useState(new Set());
  const [fTeam, setFTeam] = useState(new Set());
  const [sort, setSort] = useState({ key: "vulnerability", dir: 1 });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [f, t] = await Promise.all([api.listFindings(), api.listTests()]);
      setFindings(f);
      setTests(t);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const testName = useMemo(() => {
    const m = {};
    tests.forEach((t) => (m[t.id] = t.name));
    return m;
  }, [tests]);
  const teamName = useMemo(() => {
    const m = {};
    teams.forEach((t) => (m[t.id] = t.name));
    return m;
  }, [teams]);
  const userName = useMemo(() => {
    const m = {};
    users.forEach((u) => (m[u.id] = u.name));
    return m;
  }, [users]);

  function ownerLabel(f) {
    if (f.remediation_owner_user_id) return userName[f.remediation_owner_user_id] || "User";
    if (f.remediation_owner_team_id) return teamName[f.remediation_owner_team_id] || "Team";
    return null;
  }

  function toggle(setter, set, val) {
    const next = new Set(set);
    next.has(val) ? next.delete(val) : next.add(val);
    setter(next);
  }

  const rows = useMemo(() => {
    let r = findings.filter((f) => {
      if (fRating.size && !fRating.has(f.net_rating)) return false;
      if (fStatus.size && !fStatus.has(f.status)) return false;
      if (fSla.size && !fSla.has(f.sla_status)) return false;
      if (fTeam.size && !fTeam.has(f.remediation_owner_team_id)) return false;
      if (search) {
        const s = search.toLowerCase();
        const hay = `${f.vulnerability || ""} ${f.asset_tested || ""} ${f.finding_description || ""}`.toLowerCase();
        if (!hay.includes(s)) return false;
      }
      return true;
    });
    const { key, dir } = sort;
    r = [...r].sort((a, b) => {
      let av, bv;
      if (key === "owner") {
        av = ownerLabel(a) || "";
        bv = ownerLabel(b) || "";
      } else {
        av = a[key] ?? "";
        bv = b[key] ?? "";
      }
      return String(av).localeCompare(String(bv)) * dir;
    });
    return r;
  }, [findings, fRating, fStatus, fSla, fTeam, search, sort]);

  const outCount = rows.filter((f) => f.sla_status === "Out").length;

  function setSortKey(key) {
    setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }));
  }
  const arrow = (key) => (sort.key === key ? (sort.dir === 1 ? "▲" : "▼") : "");

  return (
    <div className="wrap">
      <aside className="rail">
        <div className="group">
          <h4>Net Rating</h4>
          {NET_RATINGS.map((r) => (
            <button
              key={r}
              className={"pill" + (fRating.has(r) ? " on" : "")}
              onClick={() => toggle(setFRating, fRating, r)}
            >
              <span className={"sw " + ratingBg(r)} />
              {r}
            </button>
          ))}
        </div>
        <div className="group">
          <h4>Status</h4>
          {FINDING_STATUSES.map((s) => (
            <button
              key={s}
              className={"pill" + (fStatus.has(s) ? " on" : "")}
              onClick={() => toggle(setFStatus, fStatus, s)}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="group">
          <h4>SLA</h4>
          {SLA_OPTS.map((s) => (
            <button
              key={s}
              className={"pill" + (fSla.has(s) ? " on" : "")}
              onClick={() => toggle(setFSla, fSla, s)}
            >
              {s === "In" ? "In SLA" : "Out of SLA"}
            </button>
          ))}
        </div>
        {teams.length > 0 && (
          <div className="group">
            <h4>Owner team</h4>
            {teams.map((t) => (
              <button
                key={t.id}
                className={"pill" + (fTeam.has(t.id) ? " on" : "")}
                onClick={() => toggle(setFTeam, fTeam, t.id)}
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
      </aside>

      <div className="main">
        <div className="list">
          <div className="toolbar">
            <input
              className="search"
              placeholder="Search findings, assets, vulnerabilities…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <span className="count">
              {rows.length} findings · {outCount} out of SLA
            </span>
            <div className="spacer" />
            <button className="btn ghost" onClick={() => setShowImport(true)}>
              Import CSV
            </button>
          </div>

          {loading ? (
            <div className="loading">Loading findings…</div>
          ) : error ? (
            <div className="empty">{error}</div>
          ) : rows.length === 0 ? (
            <div className="empty">No findings match these filters.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th className="spine" />
                  <th onClick={() => setSortKey("vulnerability")}>
                    Vulnerability <span className="ar">{arrow("vulnerability")}</span>
                  </th>
                  <th onClick={() => setSortKey("asset_tested")}>
                    Asset <span className="ar">{arrow("asset_tested")}</span>
                  </th>
                  <th>Gross → Net</th>
                  <th onClick={() => setSortKey("status")}>
                    Status <span className="ar">{arrow("status")}</span>
                  </th>
                  <th onClick={() => setSortKey("owner")}>
                    Owner <span className="ar">{arrow("owner")}</span>
                  </th>
                  <th onClick={() => setSortKey("due_date")}>
                    Due <span className="ar">{arrow("due_date")}</span>
                  </th>
                  <th onClick={() => setSortKey("sla_status")}>
                    SLA <span className="ar">{arrow("sla_status")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((f) => {
                  const owner = ownerLabel(f);
                  return (
                    <tr
                      key={f.id}
                      className={selected?.id === f.id ? "sel" : ""}
                      onClick={() => setSelected(f)}
                    >
                      <td className="spine">
                        <div className={ratingBg(f.net_rating)} />
                      </td>
                      <td className="vuln">{f.vulnerability || <span className="muted">Untitled</span>}</td>
                      <td className="muted">{f.asset_tested || "—"}</td>
                      <td>
                        <span className="delta">
                          <span className={ratingClass(f.gross_risk_rating)}>
                            {f.gross_risk_rating || "—"}
                          </span>
                          <span className="arrow">→</span>
                          <span className={ratingClass(f.net_rating)}>{f.net_rating || "—"}</span>
                        </span>
                      </td>
                      <td>
                        <span className="status">
                          <span className={"d " + statusDot(f.status)} />
                          {f.status}
                        </span>
                      </td>
                      <td className={owner ? "owner" : "owner muted"}>{owner || "— unassigned"}</td>
                      <td className="muted">{fmtDate(f.due_date)}</td>
                      <td>
                        <span className={"sla " + f.sla_status}>{f.sla_status}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {selected && (
          <FindingDrawer
            key={selected.id}
            finding={selected}
            teams={teams}
            users={users}
            testName={testName[selected.test_id]}
            onClose={() => setSelected(null)}
            onSaved={(updated) => {
              setFindings((list) => list.map((x) => (x.id === updated.id ? updated : x)));
              setSelected(updated);
            }}
          />
        )}
      </div>

      {showImport && (
        <ImportModal
          onClose={() => setShowImport(false)}
          onDone={() => {
            setShowImport(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function FindingDrawer({ finding, teams, users, testName, onClose, onSaved }) {
  const [form, setForm] = useState({ ...finding });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [atts, setAtts] = useState([]);
  const ownerKey =
    finding.remediation_owner_user_id != null
      ? `u:${finding.remediation_owner_user_id}`
      : finding.remediation_owner_team_id != null
      ? `t:${finding.remediation_owner_team_id}`
      : "";
  const [owner, setOwner] = useState(ownerKey);

  useEffect(() => {
    api.listFindingAttachments(finding.id).then(setAtts).catch(() => {});
  }, [finding.id]);

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function save() {
    setBusy(true);
    setErr("");
    const body = {
      vulnerability: form.vulnerability,
      asset_tested: form.asset_tested,
      finding_description: form.finding_description,
      net_risk_rationale: form.net_risk_rationale,
      status: form.status,
      due_date: form.due_date || null,
      gross_risk_rating: form.gross_risk_rating,
      net_rating: form.net_rating,
      net_likelihood: form.net_likelihood,
      net_impact: form.net_impact,
      itsm_reference: form.itsm_reference,
      resolver_reference: form.resolver_reference,
    };
    if (owner.startsWith("u:")) {
      body.remediation_owner_user_id = Number(owner.slice(2));
      body.remediation_owner_team_id = null;
    } else if (owner.startsWith("t:")) {
      body.remediation_owner_team_id = Number(owner.slice(2));
      body.remediation_owner_user_id = null;
    } else {
      body.remediation_owner_user_id = null;
      body.remediation_owner_team_id = null;
    }
    try {
      const updated = await api.updateFinding(finding.id, body);
      onSaved(updated);
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
      await api.uploadFindingAttachment(finding.id, file);
      setAtts(await api.listFindingAttachments(finding.id));
    } catch (e2) {
      setErr(e2.message);
    }
  }

  return (
    <aside className="drawer">
      <div className="dh">
        <button className="closeX" onClick={onClose}>
          ×
        </button>
        <span className={"sev " + ratingClass(form.net_rating)}>
          <span className={"sw " + ratingBg(form.net_rating)} />
          {form.net_rating || "Unrated"} · Net
        </span>
        <div className="vt">{form.vulnerability || "Untitled finding"}</div>
        <div className="muted" style={{ fontSize: 12 }}>
          {testName ? `Test: ${testName}` : "Unlinked"} · {form.asset_tested || "no asset"}
        </div>
      </div>
      <div className="body">
        <div className="field">
          <label>Vulnerability</label>
          <input className="in" value={form.vulnerability || ""} onChange={(e) => set("vulnerability", e.target.value)} />
        </div>
        <div className="field">
          <label>Status</label>
          <select value={form.status} onChange={(e) => set("status", e.target.value)}>
            {FINDING_STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="row2">
          <div className="field">
            <label>Remediation owner</label>
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">— unassigned</option>
              <optgroup label="Teams">
                {teams.map((t) => (
                  <option key={t.id} value={`t:${t.id}`}>
                    {t.name}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Individuals">
                {users.map((u) => (
                  <option key={u.id} value={`u:${u.id}`}>
                    {u.name}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
          <div className="field">
            <label>Due date</label>
            <input className="in" type="date" value={form.due_date || ""} onChange={(e) => set("due_date", e.target.value)} />
          </div>
        </div>
        <div className="row2">
          <div className="field">
            <label>Gross risk</label>
            <select value={form.gross_risk_rating || ""} onChange={(e) => set("gross_risk_rating", e.target.value)}>
              <option value="">—</option>
              {NET_RATINGS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Net rating</label>
            <select value={form.net_rating || ""} onChange={(e) => set("net_rating", e.target.value)}>
              <option value="">—</option>
              {NET_RATINGS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="row2">
          <div className="field">
            <label>Net likelihood</label>
            <select value={form.net_likelihood || ""} onChange={(e) => set("net_likelihood", e.target.value)}>
              <option value="">—</option>
              {LIKELIHOOD_IMPACT.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Net impact</label>
            <select value={form.net_impact || ""} onChange={(e) => set("net_impact", e.target.value)}>
              <option value="">—</option>
              {LIKELIHOOD_IMPACT.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Finding description</label>
          <textarea value={form.finding_description || ""} onChange={(e) => set("finding_description", e.target.value)} />
        </div>
        <div className="field">
          <label>Net risk rationale</label>
          <textarea value={form.net_risk_rationale || ""} onChange={(e) => set("net_risk_rationale", e.target.value)} />
        </div>
        {form.test_vendor_initial_recommendation && (
          <div className="field">
            <label>Test vendor recommendation</label>
            <div className="val muted">{form.test_vendor_initial_recommendation}</div>
          </div>
        )}
        <div className="row2">
          <div className="field">
            <label>ITSM reference</label>
            <input className="in" value={form.itsm_reference || ""} onChange={(e) => set("itsm_reference", e.target.value)} />
          </div>
          <div className="field">
            <label>Resolver reference</label>
            <input className="in" value={form.resolver_reference || ""} onChange={(e) => set("resolver_reference", e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Attachments</label>
          {atts.map((a) => (
            <div className="att" key={a.id}>
              <span className="ic">▣</span>
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  api.downloadFindingAttachment(a.id, a.filename).catch((err) => setErr(err.message));
                }}
              >
                {a.filename}
              </a>
              <button
                className="att-remove"
                title="Remove attachment"
                onClick={async () => {
                  try {
                    await api.deleteFindingAttachment(a.id);
                    setAtts(await api.listFindingAttachments(finding.id));
                  } catch (e2) {
                    setErr(e2.message);
                  }
                }}
              >
                ×
              </button>
            </div>
          ))}
          <label className="btn ghost" style={{ width: "100%", marginTop: 4, display: "block", textAlign: "center" }}>
            Upload file
            <input type="file" style={{ display: "none" }} onChange={upload} />
          </label>
        </div>
        {err && <p className="err">{err}</p>}
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={save}>
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
    </aside>
  );
}
