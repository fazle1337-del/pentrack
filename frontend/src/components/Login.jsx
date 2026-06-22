import { useEffect, useState } from "react";
import { api, ApiError, SSO_LOGIN_URL } from "../api.js";

const SSO_ERRORS = {
  no_role: "Your account isn't mapped to a Pen Test Tracker role. Contact your administrator.",
  local_account: "This email belongs to a local account. Sign in with its password below.",
  login_failed: "Single sign-on failed. Please try again or use a local account.",
};

export default function Login({ onLoggedIn, ssoError }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [ssoEnabled, setSsoEnabled] = useState(false);

  useEffect(() => {
    api
      .getAuthConfig()
      .then((c) => setSsoEnabled(!!c.sso_enabled))
      .catch(() => setSsoEnabled(false));
  }, []);

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
        {ssoError && <p className="err">{SSO_ERRORS[ssoError] || "Single sign-on failed."}</p>}
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
        {ssoEnabled && (
          <>
            <div className="sso-divider">
              <span>or</span>
            </div>
            <a className="btn btn-sso" href={SSO_LOGIN_URL}>
              Sign in with Microsoft
            </a>
          </>
        )}
        {err && <p className="err">{err}</p>}
      </div>
    </div>
  );
}
