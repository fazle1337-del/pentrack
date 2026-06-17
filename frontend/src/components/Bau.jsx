import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { ENGAGEMENT_STATUSES, engagementClass } from "../constants.js";

const WEEK_W = 26; // px per week column
const MS_WEEK = 7 * 24 * 3600 * 1000;
const GUTTER = 210;

function startOfWeek(d) {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7; // Monday = 0
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}
function addMonths(d, n) {
  const x = new Date(d);
  x.setMonth(x.getMonth() + n);
  return x;
}
function isoDate(d) {
  const x = new Date(d);
  const pad = (n) => String(n).padStart(2, "0");
  return `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}`;
}
function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fromLocalInput(s) {
  return s ? new Date(s).toISOString() : null;
}

const DEFAULT_FROM = isoDate(startOfWeek(addMonths(new Date(), -9)));
const DEFAULT_TO = isoDate(addMonths(new Date(), 9));

function blankBooking() {
  const s = new Date(); s.setHours(9, 0, 0, 0);
  const e = new Date(); e.setHours(17, 0, 0, 0);
  return {
    __new: true, title: "", unique_test_reference: "",
    start_at: s.toISOString(), end_at: e.toISOString(), status: "Scheduled",
  };
}

export default function Bau() {
  const [bookings, setBookings] = useState([]);
  const [tests, setTests] = useState([]);
  const [scopes, setScopes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [dragId, setDragId] = useState(null);
  const [from, setFrom] = useState(() => localStorage.getItem("bau_from") || DEFAULT_FROM);
  const [to, setTo] = useState(() => localStorage.getItem("bau_to") || DEFAULT_TO);

  useEffect(() => localStorage.setItem("bau_from", from), [from]);
  useEffect(() => localStorage.setItem("bau_to", to), [to]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [b, t, s] = await Promise.all([
        api.listBookings(), api.listTests(), api.listScopes(),
      ]);
      setBookings(b);
      setTests(t);
      setScopes(s);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  const testByRef = useMemo(() => {
    const m = {};
    tests.forEach((t) => t.unique_test_reference && (m[t.unique_test_reference] = t));
    return m;
  }, [tests]);
  const scopeByRef = useMemo(() => {
    const m = {};
    scopes.forEach((s) => s.unique_test_reference && (m[s.unique_test_reference] = s));
    return m;
  }, [scopes]);

  const weeks = useMemo(() => {
    const out = [];
    let c = startOfWeek(new Date(from));
    const end = new Date(to);
    let guard = 0;
    while (c <= end && guard < 520) {
      out.push(new Date(c));
      c = new Date(c.getTime() + MS_WEEK);
      guard++;
    }
    return out;
  }, [from, to]);

  const gridStart = weeks.length ? weeks[0] : startOfWeek(new Date(from));
  const totalW = Math.max(weeks.length * WEEK_W, 200);

  const months = useMemo(() => {
    const bands = [];
    weeks.forEach((w) => {
      const key = `${w.getFullYear()}-${w.getMonth()}`;
      const last = bands[bands.length - 1];
      if (last && last.key === key) last.count++;
      else bands.push({ key, count: 1, label: w.toLocaleString("en-GB", { month: "short", year: "2-digit" }) });
    });
    return bands;
  }, [weeks]);

  function barGeom(b) {
    const s = new Date(b.start_at).getTime();
    const e = new Date(b.end_at).getTime();
    const left = ((s - gridStart.getTime()) / MS_WEEK) * WEEK_W;
    const width = Math.max(((e - s) / MS_WEEK) * WEEK_W, 10);
    return { left, width };
  }

  function onDrop(targetId) {
    if (dragId == null || dragId === targetId) return;
    const arr = [...bookings];
    const fromIdx = arr.findIndex((b) => b.id === dragId);
    const toIdx = arr.findIndex((b) => b.id === targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    const [moved] = arr.splice(fromIdx, 1);
    arr.splice(toIdx, 0, moved);
    setBookings(arr);
    setDragId(null);
    api.reorderBookings(arr.map((b) => b.id)).catch((e) => setError(e.message));
  }

  return (
    <div className="sched">
      <div className="sched-toolbar">
        <span>
          <label>From</label>
          <input className="in" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </span>
        <span>
          <label>To</label>
          <input className="in" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </span>
        <button className="btn ghost" onClick={() => { setFrom(DEFAULT_FROM); setTo(DEFAULT_TO); }}>
          Reset to 18 months
        </button>
        <span className="count">{bookings.length} bookings</span>
        <div className="spacer" />
        <div className="sched-legend">
          {ENGAGEMENT_STATUSES.map((s) => (
            <span key={s}><span className={"sw " + engagementClass(s)} />{s}</span>
          ))}
        </div>
        <button className="btn" onClick={() => setSelected(blankBooking())}>+ Add booking</button>
      </div>

      <div className="sched-main">
        {loading ? (
          <div className="loading">Loading schedule…</div>
        ) : error ? (
          <div className="empty">{error}</div>
        ) : (
          <div className="sched-scroll">
            <div className="sched-grid" style={{ width: GUTTER + totalW }}>
              <div className="sched-head">
                <div className="sched-gutter" />
                <div className="sched-track" style={{ width: totalW }}>
                  <div className="sched-months">
                    {months.map((m, i) => (
                      <div className="sched-month" key={i} style={{ width: m.count * WEEK_W }}>
                        {m.label}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {bookings.length === 0 ? (
                <div className="empty">No bookings yet. Use “Add booking”.</div>
              ) : (
                bookings.map((b) => {
                  const { left, width } = barGeom(b);
                  return (
                    <div
                      className="sched-row"
                      key={b.id}
                      draggable
                      onDragStart={() => setDragId(b.id)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => onDrop(b.id)}
                    >
                      <div className="sched-gutter">
                        <span className="drag" title="Drag to reorder">≡</span>
                        <span className="bk-title" title={b.title}>{b.title || "Untitled"}</span>
                      </div>
                      <div className="sched-track" style={{ width: totalW }}>
                        <div
                          className={"bk-bar " + engagementClass(b.status)}
                          style={{ left, width }}
                          onClick={() => setSelected(b)}
                          title={`${b.title} · ${b.status}`}
                        >
                          <span className="bk-bar-label">{b.title || "Untitled"}</span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {selected && (
          <BookingDrawer
            key={selected.id || "new"}
            booking={selected}
            testByRef={testByRef}
            scopeByRef={scopeByRef}
            onClose={() => setSelected(null)}
            onSaved={() => { setSelected(null); load(); }}
            onDeleted={() => { setSelected(null); load(); }}
          />
        )}
      </div>
    </div>
  );
}

function BookingDrawer({ booking, testByRef, scopeByRef, onClose, onSaved, onDeleted }) {
  const isNew = !!booking.__new;
  const [form, setForm] = useState({
    title: booking.title || "",
    unique_test_reference: booking.unique_test_reference || "",
    start_at: booking.start_at || null,
    end_at: booking.end_at || null,
    status: booking.status || "Scheduled",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  const ref = (form.unique_test_reference || "").trim();
  const linkedTest = ref ? testByRef[ref] : null;
  const linkedScope = ref ? scopeByRef[ref] : null;

  async function save() {
    if (!form.title.trim()) { setErr("Title is required"); return; }
    if (!form.start_at || !form.end_at) { setErr("Start and end are required"); return; }
    if (new Date(form.end_at) < new Date(form.start_at)) { setErr("End must be after start"); return; }
    setBusy(true);
    setErr("");
    const body = {
      title: form.title,
      unique_test_reference: form.unique_test_reference || null,
      start_at: form.start_at,
      end_at: form.end_at,
      status: form.status,
    };
    try {
      if (isNew) await api.createBooking(body);
      else await api.updateBooking(booking.id, body);
      onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function del() {
    if (!window.confirm("Delete this booking?")) return;
    try {
      await api.deleteBooking(booking.id);
      onDeleted();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <aside className="drawer">
      <div className="dh">
        <button className="closeX" onClick={onClose}>×</button>
        <div className="vt">{isNew ? "New booking" : form.title || "Booking"}</div>
        <div className="muted" style={{ fontSize: 12 }}>BAU schedule slot</div>
      </div>
      <div className="body">
        <div className="field">
          <label>Title</label>
          <input className="in" value={form.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="field">
          <label>Unique test reference</label>
          <input
            className="in"
            value={form.unique_test_reference}
            onChange={(e) => set("unique_test_reference", e.target.value)}
            placeholder="links to a test / scope by this key"
          />
        </div>
        <div className="row2">
          <div className="field">
            <label>Start</label>
            <input className="in" type="datetime-local" value={toLocalInput(form.start_at)}
              onChange={(e) => set("start_at", fromLocalInput(e.target.value))} />
          </div>
          <div className="field">
            <label>End</label>
            <input className="in" type="datetime-local" value={toLocalInput(form.end_at)}
              onChange={(e) => set("end_at", fromLocalInput(e.target.value))} />
          </div>
        </div>
        <div className="field">
          <label>Status</label>
          <select value={form.status} onChange={(e) => set("status", e.target.value)}>
            {ENGAGEMENT_STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>

        {ref && (
          <div className="field">
            <label>Linked by “{ref}”</label>
            <div className="val muted">
              {linkedTest ? `Test: ${linkedTest.name} (${linkedTest.status})` : "No matching test"}
              <br />
              {linkedScope ? `Scope: ${linkedScope.title}` : "No matching scope"}
            </div>
          </div>
        )}

        {!isNew && (
          <p className="muted" style={{ fontSize: 11, marginTop: -4 }}>
            Changing status here syncs to the linked test (and vice-versa).
          </p>
        )}

        {err && <p className="err">{err}</p>}
        <button className="btn" style={{ width: "100%" }} disabled={busy} onClick={save}>
          {busy ? "Saving…" : isNew ? "Create booking" : "Save changes"}
        </button>
        {!isNew && (
          <button className="btn ghost" style={{ width: "100%", marginTop: 8 }} onClick={del}>
            Delete booking
          </button>
        )}
      </div>
    </aside>
  );
}
