import { useEffect, useState } from "react";
import { api } from "../api.js";

// Admin-only panel: configure the EasyVista (ITSM) bearer token + background
// poller settings at runtime. Mirrors AccessControl.jsx's SsoConnection —
// the token is write-only (the GET never returns it, only bearer_token_set),
// and only sent to the API when the admin actually types a new one.
//
// itsm_enabled itself (whether the integration is on at all) is deployment
// env only, not editable here — see docs/easyvista-integration.md.
export default function Integrations() {
  const [itsmEnabled, setItsmEnabled] = useState(null); // null = not loaded yet
  const [cfg, setCfg] = useState(null);
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [itsmCfg, evCfg] = await Promise.all([
        api.getItsmConfig(),
        api.getEasyVistaConfig(),
      ]);
      setItsmEnabled(!!itsmCfg.itsm_enabled);
      setCfg(evCfg);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  function set(k, v) {
    setCfg((c) => ({ ...c, [k]: v }));
    setSaved(false);
  }

  async function save() {
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const body = {
        poll_enabled: cfg.poll_enabled,
        poll_open_interval_seconds: Number(cfg.poll_open_interval_seconds),
        poll_closed_interval_seconds: Number(cfg.poll_closed_interval_seconds),
        poll_closed_lookback_days: Number(cfg.poll_closed_lookback_days),
      };
      if (token) body.bearer_token = token; // only send when actually changed
      const next = await api.updateEasyVistaConfig(body);
      setCfg(next);
      setToken("");
      setSaved(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="loading">Loading integrations…</div>;

  return (
    <div className="section-pad" style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 16, margin: "4px 0 2px" }}>EasyVista (ITSM)</h2>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 16px" }}>
        Push findings to EasyVista as tickets and sync their status back. Host,
        account, and catalogue stay set at the deployment level; only the
        bearer token and poller behavior are editable here.
      </p>

      {itsmEnabled === false && (
        <div className="empty" style={{ marginBottom: 16 }}>
          The EasyVista integration isn't enabled for this deployment
          (<code>EASYVISTA_ENABLED</code>). Settings below can still be saved,
          but nothing will use them until it's turned on.
        </div>
      )}

      {error && <p className="err">{error}</p>}
      {cfg && (
        <>
          <div style={{ flex: "1 1 340px", marginBottom: 14 }}>
            <label>
              Bearer token{" "}
              {cfg.bearer_token_set && <span className="muted">(configured)</span>}
            </label>
            <input
              className="in"
              type="password"
              value={token}
              placeholder={
                cfg.bearer_token_set ? "•••••• — leave blank to keep" : "enter EV bearer token"
              }
              onChange={(e) => {
                setToken(e.target.value);
                setSaved(false);
              }}
            />
            <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>
              When EV rotates this, request it from your technician and paste
              the new value here — no redeploy needed.
            </p>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <input
              type="checkbox"
              checked={!!cfg.poll_enabled}
              onChange={(e) => set("poll_enabled", e.target.checked)}
            />
            <span>Automatically poll ticket status in the background</span>
          </label>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            <div style={{ flex: "1 1 220px" }}>
              <label>Open-finding poll interval (seconds)</label>
              <input
                className="in"
                type="number"
                min="60"
                value={cfg.poll_open_interval_seconds}
                onChange={(e) => set("poll_open_interval_seconds", e.target.value)}
              />
              <p className="muted" style={{ fontSize: 11, margin: "2px 0 0" }}>Default 86400 (daily)</p>
            </div>
            <div style={{ flex: "1 1 220px" }}>
              <label>Closed-finding poll interval (seconds)</label>
              <input
                className="in"
                type="number"
                min="60"
                value={cfg.poll_closed_interval_seconds}
                onChange={(e) => set("poll_closed_interval_seconds", e.target.value)}
              />
              <p className="muted" style={{ fontSize: 11, margin: "2px 0 0" }}>Default 604800 (weekly)</p>
            </div>
            <div style={{ flex: "1 1 220px" }}>
              <label>Stop polling closed tickets after (days)</label>
              <input
                className="in"
                type="number"
                min="1"
                value={cfg.poll_closed_lookback_days}
                onChange={(e) => set("poll_closed_lookback_days", e.target.value)}
              />
              <p className="muted" style={{ fontSize: 11, margin: "2px 0 0" }}>Default 365</p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
            <button className="btn" disabled={busy} onClick={save}>
              {busy ? "Saving…" : "Save settings"}
            </button>
            {saved && <span className="muted" style={{ fontSize: 13 }}>Saved ✓</span>}
          </div>
        </>
      )}
    </div>
  );
}
