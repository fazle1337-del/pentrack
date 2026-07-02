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

// Admin-only: create / rename / delete Teams (issue #13). Teams back the finding
// owner picker and the group→role mapping below, but had no UI — they could only
// be made via the API or CSV import. onTeamsChanged refreshes the app-wide teams
// list so those dropdowns update immediately.
//
// Also edits Team.ev_group_id (2026-07-01/02) — the EasyVista assignee-group
// mapping a pushed finding routes to. Only shown/editable when the ITSM
// integration is enabled (itsmEnabled), since there's nothing to map to
// otherwise. "Load EV groups" is a convenience picker (GET /itsm/groups) so an
// admin doesn't have to know the raw group id by heart.
function TeamsManager({ teams, onTeamsChanged, itsmEnabled }) {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(null); // { id, name, ev_group_id }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [evGroups, setEvGroups] = useState(null); // null = not loaded yet

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await onTeamsChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    const n = name.trim();
    if (!n) {
      setError("Team name is required");
      return;
    }
    await run(async () => {
      await api.createTeam(n);
      setName("");
    });
  }

  async function saveEdit() {
    const n = editing.name.trim();
    if (!n) {
      setError("Team name is required");
      return;
    }
    await run(async () => {
      await api.updateTeam(editing.id, {
        name: n,
        ev_group_id: editing.ev_group_id.trim(),
      });
      setEditing(null);
    });
  }

  async function remove(team) {
    if (!window.confirm(`Delete team "${team.name}"?`)) return;
    await run(() => api.deleteTeam(team.id));
  }

  async function loadEvGroups() {
    setError("");
    try {
      setEvGroups(await api.listEvGroups());
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div style={{ maxWidth: 760, marginBottom: 28 }}>
      <h2 style={{ fontSize: 16, margin: "4px 0 2px" }}>Teams</h2>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 16px" }}>
        Teams can own findings and be the target of a group → role mapping. A team
        that's still referenced can't be deleted until those references are
        reassigned.
        {itsmEnabled &&
          " Teams pushed to EasyVista also need an EV group mapped — that's what routes the ticket."}
      </p>

      <div className="field" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: "2 1 240px" }}>
          <label>New team name</label>
          <input
            className="in"
            value={name}
            placeholder="e.g. Payments Engineering"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
        </div>
        <button className="btn" disabled={busy} onClick={add}>
          {busy ? "Saving…" : "Add team"}
        </button>
      </div>

      {error && <p className="err">{error}</p>}

      {teams.length === 0 ? (
        <div className="empty">No teams yet. Add one so findings and group mappings can target it.</div>
      ) : (
        <div className="maptable">
          {teams.map((t) => (
            <div className="maprow" key={t.id}>
              {editing?.id === t.id ? (
                <>
                  <input
                    className="in"
                    style={{ flex: "1 1 auto" }}
                    value={editing.name}
                    autoFocus
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") saveEdit();
                      if (e.key === "Escape") setEditing(null);
                    }}
                  />
                  {itsmEnabled && (
                    <>
                      <input
                        className="in"
                        style={{ flex: "1 1 180px" }}
                        placeholder="EV group id"
                        value={editing.ev_group_id}
                        onChange={(e) => setEditing({ ...editing, ev_group_id: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveEdit();
                          if (e.key === "Escape") setEditing(null);
                        }}
                      />
                      {evGroups === null ? (
                        <button className="btn ghost" onClick={loadEvGroups}>Load EV groups…</button>
                      ) : (
                        <select
                          value=""
                          onChange={(e) =>
                            e.target.value && setEditing({ ...editing, ev_group_id: e.target.value })
                          }
                        >
                          <option value="">— pick from EV —</option>
                          {evGroups.map((g) => (
                            <option key={g.GROUP_ID} value={g.GROUP_ID}>
                              {g.GROUP_EN || g.GROUP_ID} ({g.GROUP_ID})
                            </option>
                          ))}
                        </select>
                      )}
                    </>
                  )}
                  <button className="btn" disabled={busy} onClick={saveEdit}>Save</button>
                  <button className="att-remove" title="Cancel" onClick={() => setEditing(null)}>×</button>
                </>
              ) : (
                <>
                  <div className="mapcol-name" style={{ flex: "1 1 auto" }}>
                    {t.name}
                    {itsmEnabled && t.ev_group_id && (
                      <div className="mapsample">EV group: {t.ev_group_id}</div>
                    )}
                  </div>
                  <button
                    className="btn ghost"
                    onClick={() => setEditing({ id: t.id, name: t.name, ev_group_id: t.ev_group_id || "" })}
                  >
                    Rename
                  </button>
                  <button className="att-remove" title="Delete team" onClick={() => remove(t)}>×</button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Admin-only tab: manage how identity-provider groups map to app roles.
// idp_group_id is the raw groups-claim value — a group path in Keycloak
// (e.g. /pentrack-admins) or an object-ID GUID in Entra.
export default function AccessControl({ teams, onTeamsChanged }) {
  const [maps, setMaps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ idp_group_id: "", label: "", role: "member", team_id: "" });
  const [busy, setBusy] = useState(false);
  const [itsmEnabled, setItsmEnabled] = useState(false);

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
    api.getItsmConfig().then((c) => setItsmEnabled(!!c.itsm_enabled)).catch(() => {});
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

      <TeamsManager teams={teams} onTeamsChanged={onTeamsChanged} itsmEnabled={itsmEnabled} />

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
