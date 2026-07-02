import { useEffect, useState } from "react";
import { api, setToken, consumeSsoRedirect } from "./api.js";
import Login from "./components/Login.jsx";
import Findings from "./components/Findings.jsx";
import Tests from "./components/Tests.jsx";
import Bau from "./components/Bau.jsx";
import Scopes from "./components/Scopes.jsx";
import AccessControl from "./components/AccessControl.jsx";
import Integrations from "./components/Integrations.jsx";

const BASE_TABS = ["Findings", "Tests", "BAU Schedule", "Scopes"];

// Which tab owns each related-entity type, for cross-tab navigation.
const TYPE_TAB = {
  finding: "Findings",
  test: "Tests",
  booking: "BAU Schedule",
  scope: "Scopes",
};

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [tab, setTab] = useState("Findings");
  // Pending cross-tab navigation target: { type, id }. The destination tab
  // consumes it (opens that entity's drawer) then clears it via onNavConsumed.
  const [nav, setNav] = useState(null);
  const [teams, setTeams] = useState([]);
  const [users, setUsers] = useState([]);
  const [me, setMe] = useState(null);
  const [ssoError, setSsoError] = useState("");

  // Pick up an SSO redirect result before rendering the login form.
  useEffect(() => {
    const r = consumeSsoRedirect();
    if (r?.token) setAuthed(true);
    else if (r?.error) setSsoError(r.error);
  }, []);

  async function loadRefs() {
    // teams is readable by anyone; users is admin-only and may 403 for members.
    try {
      setMe(await api.me());
    } catch {}
    try {
      setTeams(await api.listTeams());
    } catch {}
    try {
      setUsers(await api.listUsers());
    } catch {}
  }

  async function reloadTeams() {
    try {
      setTeams(await api.listTeams());
    } catch {}
  }

  useEffect(() => {
    if (authed) loadRefs();
  }, [authed]);

  async function logout() {
    // Best-effort server-side revocation; clear local state regardless.
    try {
      await api.logout();
    } catch {}
    setToken(null);
    setAuthed(false);
    setMe(null);
  }

  function navTo(type, id) {
    const dest = TYPE_TAB[type];
    if (!dest) return;
    setNav({ type, id });
    setTab(dest);
  }

  if (!authed) return <Login onLoggedIn={() => setAuthed(true)} ssoError={ssoError} />;

  const isAdmin = me?.role === "admin";
  const tabs = isAdmin ? [...BASE_TABS, "Access", "Integrations"] : BASE_TABS;
  const initials = me?.name
    ? me.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "··";

  return (
    <>
      <div className="topbar">
        <div className="brand">
          <span className="dot" /> Pen Test Tracker
        </div>
        <div className="tabs">
          {tabs.map((t) => (
            <button key={t} className={"tab" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>
        <div className="spacer" />
        <div className="who">
          <span className="av" title={me ? `${me.name} · ${me.role}` : ""}>{initials}</span>
        </div>
        <button className="logout" onClick={logout}>
          Sign out
        </button>
      </div>

      {tab === "Findings" && (
        <Findings
          teams={teams}
          users={users}
          isAdmin={isAdmin}
          me={me}
          onNavigate={navTo}
          nav={nav?.type === "finding" ? nav : null}
          onNavConsumed={() => setNav(null)}
        />
      )}
      {tab === "Tests" && (
        <Tests
          teams={teams}
          users={users}
          isAdmin={isAdmin}
          onNavigate={navTo}
          nav={nav?.type === "test" ? nav : null}
          onNavConsumed={() => setNav(null)}
        />
      )}
      {tab === "BAU Schedule" && (
        <Bau
          onNavigate={navTo}
          nav={nav?.type === "booking" ? nav : null}
          onNavConsumed={() => setNav(null)}
        />
      )}
      {tab === "Scopes" && (
        <Scopes
          onNavigate={navTo}
          nav={nav?.type === "scope" ? nav : null}
          onNavConsumed={() => setNav(null)}
        />
      )}
      {tab === "Access" && isAdmin && (
        <AccessControl teams={teams} onTeamsChanged={reloadTeams} />
      )}
      {tab === "Integrations" && isAdmin && <Integrations />}
    </>
  );
}
