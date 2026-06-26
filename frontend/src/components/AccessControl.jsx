import { useEffect, useState } from "react";
import { api } from "../api.js";

// Admin-only panel: configure the OIDC/Entra connection at runtime (issue #11),
// so onboarding a tenant needs no redeploy or host-side secret file. The client
// secret is write-only — the API returns only whether one is set, and we send a
// new secret only when the admin actually types one (blank leaves it unchanged).
const CONNECTION_FIELDS = [
  ["authority", "Authority (issuer)", "https://login.microsoftonline.com/<tenant-id>/v2.0"],
  ["client_id", "Client ID", "application (client) ID"],
  ["redirect_uri", "Redirect URI", "https://pentrack.example.com/api/auth/sso/callback"],
  ["scopes", "Scopes", "openid profile email"],
  ["groups_claim", "Groups claim", "groups"],
  ["post_login_redirect", "Post-login redirect", "/"],
];

function SsoConnection() {
  const [cfg, setCfg] = useState(null);
  const [secret, setSecret] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setCfg(await api.getOidcConfig());
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
        enabled: cfg.enabled,
        authority: cfg.authority,
        client_id: cfg.client_id,
        redirect_uri: cfg.redirect_uri,
        scopes: cfg.scopes,
        groups_claim: cfg.groups_claim,
        post_login_redirect: cfg.post_login_redirect,
      };
      if (secret) body.client_secret = secret; // only send when actually changed
      const next = await api.updateOidcConfig(body);
      setCfg(next);
      setSecret("");
      setSaved(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="loading">Loading SSO connection…</div>;
  if (!cfg) return error ? <p className="err">{error}</p> : null;

  return (
    <div style={{ maxWidth: 760, marginBottom: 28 }}>
      <h2 style={{ fontSize: 16, margin: "4px 0 2px" }}>SSO connection</h2>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 16px" }}>
        Point the app at your OIDC/Entra tenant. Changes take effect on the next
        sign-in — no redeploy. Local (break-glass) login always works, so a bad
        config can be fixed here.
      </p>

      <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <input
          type="checkbox"
          checked={!!cfg.enabled}
          onChange={(e) => set("enabled", e.target.checked)}
        />
        <span>SSO enabled</span>
      </label>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {CONNECTION_FIELDS.map(([key, label, ph]) => (
          <div key={key} style={{ flex: "1 1 340px" }}>
            <label>{label}</label>
            <input
              className="in"
              value={cfg[key] || ""}
              placeholder={ph}
              onChange={(e) => set(key, e.target.value)}
            />
          </div>
        ))}
        <div style={{ flex: "1 1 340px" }}>
          <label>
            Client secret{" "}
            {cfg.client_secret_set && <span className="muted">(configured)</span>}
          </label>
          <input
            className="in"
            type="password"
            value={secret}
            placeholder={cfg.client_secret_set ? "•••••• — leave blank to keep" : "enter client secret"}
            onChange={(e) => {
              setSecret(e.target.value);
              setSaved(false);
            }}
          />
        </div>
      </div>

      {error && <p className="err">{error}</p>}

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
        <button className="btn" disabled={busy} onClick={save}>
          {busy ? "Saving…" : "Save connection"}
        </button>
        {saved && <span className="muted" style={{ fontSize: 13 }}>Saved ✓</span>}
      </div>
    </div>
  );
}

// Admin-only tab: manage how identity-provider groups map to app roles.
// idp_group_id is the raw groups-claim value — a group path in Keycloak
// (e.g. /pentrack-admins) or an object-ID GUID in Entra.
export default function AccessControl({ teams }) {
  const [maps, setMaps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ idp_group_id: "", label: "", role: "member", team_id: "" });
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setMaps(await api.listIdpRoleMaps());
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
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function add() {
    if (!form.idp_group_id.trim()) {
      setError("Group identifier is required");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.createIdpRoleMap({
        idp_group_id: form.idp_group_id.trim(),
        label: form.label.trim() || null,
        role: form.role,
        team_id: form.team_id ? Number(form.team_id) : null,
      });
      setForm({ idp_group_id: "", label: "", role: "member", team_id: "" });
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id) {
    if (!window.confirm("Remove this group → role mapping?")) return;
    try {
      await api.deleteIdpRoleMap(id);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const teamName = (id) => teams.find((t) => t.id === id)?.name;

  return (
    <div className="section-pad" style={{ maxWidth: 760 }}>
      <SsoConnection />

      <h2 style={{ fontSize: 16, margin: "4px 0 2px" }}>SSO access control</h2>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 16px" }}>
        Map identity-provider groups to roles. At SSO sign-in a user's groups are
        looked up here and the highest-privilege match wins. Local (break-glass)
        accounts are unaffected.
      </p>

      <div className="field" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: "2 1 220px" }}>
          <label>Group identifier</label>
          <input
            className="in"
            value={form.idp_group_id}
            placeholder="/pentrack-admins  or  Entra group GUID"
            onChange={(e) => set("idp_group_id", e.target.value)}
          />
        </div>
        <div style={{ flex: "1 1 140px" }}>
          <label>Label (optional)</label>
          <input className="in" value={form.label} onChange={(e) => set("label", e.target.value)} />
        </div>
        <div style={{ flex: "0 1 120px" }}>
          <label>Role</label>
          <select value={form.role} onChange={(e) => set("role", e.target.value)}>
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
        </div>
        <div style={{ flex: "0 1 150px" }}>
          <label>Team (optional)</label>
          <select value={form.team_id} onChange={(e) => set("team_id", e.target.value)}>
            <option value="">— none —</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
        <button className="btn" disabled={busy} onClick={add}>
          {busy ? "Adding…" : "Add mapping"}
        </button>
      </div>

      {error && <p className="err">{error}</p>}

      {loading ? (
        <div className="loading">Loading mappings…</div>
      ) : maps.length === 0 ? (
        <div className="empty">No mappings yet. SSO users won't be able to sign in until at least one group is mapped.</div>
      ) : (
        <div className="maptable">
          {maps.map((m) => (
            <div className="maprow" key={m.id}>
              <div className="mapcol-name">
                {m.label || m.idp_group_id}
                <div className="mapsample">{m.idp_group_id}</div>
              </div>
              <span className="mapcol-arrow">→</span>
              <span className="badge">{m.role}</span>
              <span className="muted" style={{ fontSize: 12, minWidth: 90 }}>
                {m.team_id ? teamName(m.team_id) || `team #${m.team_id}` : ""}
              </span>
              <button className="att-remove" title="Remove mapping" onClick={() => remove(m.id)}>×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
