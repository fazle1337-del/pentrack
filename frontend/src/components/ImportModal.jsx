import { useEffect, useState } from "react";
import { api } from "../api.js";

const FIELD_LABELS = {
  // test
  name: "Test · Name",
  tester_reference: "Test · Tester + Reference",
  scope: "Test · Scope",
  bau_or_project: "Test · BAU / Project",
  itsm_reference: "Test · ITSM Reference",
  date_logged: "Test · Date Logged",
  due_date: "Test · Due Date",
  scheduled_date: "Test · Scheduled Date",
  // finding
  asset_tested: "Finding · Asset Tested",
  user_story: "Finding · User Story",
  vulnerability: "Finding · Vulnerability",
  finding_description: "Finding · Description",
  test_vendor_initial_recommendation: "Finding · Vendor Recommendation",
  gross_risk_rating: "Finding · Gross Risk Rating",
  net_likelihood: "Finding · Net Likelihood",
  net_impact: "Finding · Net Impact",
  net_rating: "Finding · Net Rating",
  net_risk_rationale: "Finding · Net Risk Rationale",
  status: "Finding · Status",
  additional_information: "Finding · Additional Information",
  resolver_reference: "Finding · Resolver Reference",
  date_logged_in_resolver: "Finding · Date Logged in Resolver",
};

// Auto-match a CSV header to a target field. Conservative on purpose: a wrong
// default that looks right is worse than no default, since users trust it. Only
// exact normalised matches and a small set of known aliases are applied; anything
// ambiguous is left blank for the user to set.
const ALIASES = {
  name: ["testname", "engagement", "title"],
  vulnerability: ["vuln", "finding", "issue"],
  asset_tested: ["asset", "assettested", "target", "host"],
  finding_description: ["description", "details", "summary"],
  gross_risk_rating: ["gross", "grossrisk", "grossrating"],
  net_rating: ["net", "netrating", "netrisk", "rating", "severity"],
  net_likelihood: ["netlikelihood", "likelihood"],
  net_impact: ["netimpact", "impact"],
  status: ["status", "state"],
  tester_reference: ["tester", "vendor", "testerreference"],
  due_date: ["due", "duedate", "deadline"],
  scope: ["scope"],
  bau_or_project: ["bauproject", "bauorproject"],
  itsm_reference: ["itsm", "itsmreference", "ticket"],
};

function autoMatch(header, fields) {
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const h = norm(header);
  // 1. exact match against the field name itself
  for (const f of fields) {
    if (norm(f) === h) return f;
  }
  // 2. exact match against a known alias (only if that field is offered)
  for (const f of fields) {
    const aliases = ALIASES[f] || [];
    if (aliases.includes(h)) return f;
  }
  return ""; // ambiguous -> leave for the user
}

export default function ImportModal({ onClose, onDone }) {
  const [step, setStep] = useState("upload"); // upload | map | done
  const [file, setFile] = useState(null);
  const [fields, setFields] = useState({ test_fields: [], finding_fields: [] });
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState(null);

  useEffect(() => {
    api.importFields().then(setFields).catch((e) => setErr(e.message));
  }, []);

  const allFields = [...fields.test_fields, ...fields.finding_fields];

  async function onPick(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setErr("");
    setBusy(true);
    try {
      const pv = await api.importPreview(f);
      setPreview(pv);
      // pre-fill mapping with auto-matches
      const m = {};
      pv.headers.forEach((h) => {
        // findings-centric import: prefer finding fields on ambiguous names
        m[h] = autoMatch(h, [...fields.finding_fields, ...fields.test_fields]);
      });
      setMapping(m);
      setStep("map");
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    setBusy(true);
    setErr("");
    try {
      const res = await api.importCommit(file, mapping, "new");
      setReport(res);
      setStep("done");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const mappedTargets = Object.values(mapping).filter(Boolean);
  const hasName = mappedTargets.includes("name");
  const hasVuln = mappedTargets.includes("vulnerability");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Import CSV</h2>
          <button className="closeX" onClick={onClose}>
            ×
          </button>
        </div>

        {step === "upload" && (
          <div className="modal-body">
            <p className="muted">
              Upload a CSV where each row is one finding. Test details (name, scope, etc.)
              should repeat on every row — they're taken from the first row to create one test.
            </p>
            <label className="btn" style={{ display: "inline-block", marginTop: 12 }}>
              Choose CSV file
              <input type="file" accept=".csv,text/csv" style={{ display: "none" }} onChange={onPick} />
            </label>
            {busy && <p className="muted">Reading file…</p>}
          </div>
        )}

        {step === "map" && preview && (
          <div className="modal-body">
            <p className="muted">
              {preview.row_count} rows. Map each CSV column to a field, or leave as “Ignore”.
            </p>
            <div className="maptable">
              {preview.headers.map((h) => (
                <div className="maprow" key={h}>
                  <div className="mapcol-name" title={h}>
                    {h}
                    <div className="mapsample">
                      {preview.sample.map((r) => r[h]).filter(Boolean)[0] || ""}
                    </div>
                  </div>
                  <div className="mapcol-arrow">→</div>
                  <select
                    value={mapping[h] || ""}
                    onChange={(e) => setMapping((m) => ({ ...m, [h]: e.target.value }))}
                  >
                    <option value="">Ignore this column</option>
                    <optgroup label="Test fields">
                      {fields.test_fields.map((f) => (
                        <option key={f} value={f}>
                          {FIELD_LABELS[f] || f}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="Finding fields">
                      {fields.finding_fields.map((f) => (
                        <option key={f} value={f}>
                          {FIELD_LABELS[f] || f}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                </div>
              ))}
            </div>

            {!hasName && (
              <p className="warnline">
                No column mapped to <strong>Test · Name</strong> — the test will be named after the file.
              </p>
            )}
            {!hasVuln && (
              <p className="warnline">
                Tip: map a column to <strong>Finding · Vulnerability</strong> so findings have titles.
              </p>
            )}
            {err && <p className="err">{err}</p>}
            <div className="modal-actions">
              <button className="btn ghost" onClick={() => setStep("upload")}>
                Back
              </button>
              <button className="btn" disabled={busy} onClick={commit}>
                {busy ? "Importing…" : `Import ${preview.row_count} findings`}
              </button>
            </div>
          </div>
        )}

        {step === "done" && report && (
          <div className="modal-body">
            <p>
              Imported <strong>{report.findings_created}</strong> findings into{" "}
              <strong>{report.test_name}</strong>.
            </p>
            {report.issue_count > 0 ? (
              <>
                <p className="warnline">
                  {report.issue_count} value{report.issue_count === 1 ? "" : "s"} couldn't be read and
                  were left blank. Fix them in the findings list when ready:
                </p>
                <div className="issuelist">
                  {report.issues.map((i, idx) => (
                    <div className="issue" key={idx}>
                      <span className="badge">Row {i.row}</span>
                      <span className="muted">{i.field}</span> — {i.message}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">No issues — every value imported cleanly.</p>
            )}
            <div className="modal-actions">
              <button className="btn" onClick={onDone}>
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
