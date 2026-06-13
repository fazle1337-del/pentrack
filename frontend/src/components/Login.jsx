import { useState } from "react";
import { api, ApiError } from "../api.js";

export default function Login({ onLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr("");
    setBusy(true);
    try {
      await api.login(email, password);
      onLoggedIn();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="card">
        <h1>
          <span className="brand">
            <span className="dot" />
          </span>
          Pen Test Tracker
        </h1>
        <p>Sign in to view and manage findings.</p>
        <div className="field">
          <label>Email</label>
          <input
            className="in"
            value={email}
            autoFocus
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
        </div>
        <div className="field">
          <label>Password</label>
          <input
            className="in"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
        </div>
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={submit}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {err && <p className="err">{err}</p>}
      </div>
    </div>
  );
}
