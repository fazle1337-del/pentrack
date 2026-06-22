import { useEffect, useState } from "react";
import { api, setToken, consumeSsoRedirect } from "./api.js";
import Login from "./components/Login.jsx";
import Findings from "./components/Findings.jsx";
import Tests from "./components/Tests.jsx";
import Bau from "./components/Bau.jsx";
import Scopes from "./components/Scopes.jsx";
import AccessControl from "./components/AccessControl.jsx";

const BASE_TABS = ["Findings", "Tests", "BAU Schedule", "Scopes"];

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [tab, setTab] = useState("Findings");
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

  useEffect(() => {
    if (authed) loadRefs();
  }, [authed]);

  function logout() {
    setToken(null);
    setAuthed(false);
    setMe(null);
  }

  if (!authed) return <Login onLoggedIn={() => setAuthed(true)} ssoError={ssoError} />;

  const isAdmin = me?.role === "admin";
  const tabs = isAdmin ? [...BASE_TABS, "Access"] : BASE_TABS;
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

      {tab === "Findings" && <Findings teams={teams} users={users} />}
      {tab === "Tests" && <Tests teams={teams} users={users} />}
      {tab === "BAU Schedule" && <Bau />}
      {tab === "Scopes" && <Scopes />}
      {tab === "Access" && isAdmin && <AccessControl teams={teams} />}
    </>
  );
}
