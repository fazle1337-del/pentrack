import { useEffect, useState } from "react";
import { api } from "../api.js";

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
