import { useEffect, useState } from "react";
import { api } from "../api.js";

// Human label per entity type returned by GET /related.
const TYPE_LABEL = {
  test: "Test",
  finding: "Finding",
  booking: "BAU booking",
  scope: "Scope",
};

// Lists every entity sharing this drawer's unique_test_reference and lets the
// user jump to it. `self` ({ type, id }) is the entity owning the panel and is
// hidden from its own related list. `onNavigate(type, id)` switches tab + opens.
export default function RelatedPanel({ reference, self, onNavigate }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState("");
  const ref = (reference || "").trim();

  useEffect(() => {
    if (!ref) {
      setItems([]);
      return;
    }
    let alive = true;
    setErr("");
    // Debounce: the ref field is editable, so don't fetch on every keystroke.
    const timer = setTimeout(() => {
      api
        .getRelated(ref)
        .then((r) => alive && setItems(r))
        .catch((e) => alive && setErr(e.message));
    }, 250);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [ref]);

  if (!ref) return null;

  const list = (items || []).filter(
    (i) => !(self && i.type === self.type && i.id === self.id)
  );

  return (
    <div className="field">
      <label>Related — linked by “{ref}”</label>
      {err ? (
        <div className="muted">{err}</div>
      ) : items == null ? (
        <div className="muted">Loading…</div>
      ) : list.length === 0 ? (
        <div className="muted">Nothing else shares this reference.</div>
      ) : (
        list.map((i) => (
          <button
            type="button"
            key={`${i.type}:${i.id}`}
            className="related-link"
            onClick={() => onNavigate?.(i.type, i.id)}
            title={`Open ${TYPE_LABEL[i.type] || i.type}`}
          >
            <span className="related-type">{TYPE_LABEL[i.type] || i.type}</span>
            <span className="related-label">{i.label || "Untitled"}</span>
            {i.sub && <span className="related-sub">{i.sub}</span>}
          </button>
        ))
      )}
    </div>
  );
}
