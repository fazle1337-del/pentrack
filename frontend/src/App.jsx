import { useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import Login from "./components/Login.jsx";
import Findings from "./components/Findings.jsx";
import Tests from "./components/Tests.jsx";
import Bau from "./components/Bau.jsx";
import Scopes from "./components/Scopes.jsx";

const TABS = ["Findings", "Tests", "BAU Schedule", "Scopes"];

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [tab, setTab] = useState("Findings");
  const [teams, setTeams] = useState([]);
  const [users, setUsers] = useState([]);

  async function loadRefs() {
    // teams is readable by anyone; users is admin-only and may 403 for members.
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
  }

  if (!authed) return <Login onLoggedIn={() => setAuthed(true)} />;

  return (
    <>
      <div className="topbar">
        <div className="brand">
          <span className="dot" /> Pen Test Tracker
        </div>
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t} className={"tab" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>
        <div className="spacer" />
        <div className="who">
          <span className="av">IS</span>
        </div>
        <button className="logout" onClick={logout}>
          Sign out
        </button>
      </div>

      {tab === "Findings" && <Findings teams={teams} users={users} />}
      {tab === "Tests" && <Tests teams={teams} users={users} />}
      {tab === "BAU Schedule" && <Bau />}
      {tab === "Scopes" && <Scopes />}
    </>
  );
}
