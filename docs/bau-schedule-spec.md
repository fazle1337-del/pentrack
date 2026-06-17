# Spec: BAU Schedule, shared reference key, and Scopes redesign

Status: **DRAFT — awaiting sign-off.** No code until approved.

Builds three coupled pieces together (per Tony: build all, then test):
1. **BAU Schedule** — a new `Booking` entity with a weekly timeline view.
2. **Shared key** — `unique_test_reference` becomes the one linking key across all tabs.
3. **Scopes redesign** — `Scope` becomes a real entity (title + attachments), replacing the free-text `Test.scope`.

Context: app is **not in production use**, so data preservation is not required — migrations can be destructive where convenient.

---

## 1. Data model

### 1.1 New enum `EngagementStatus` (replaces `TestStatus`)
Shared by `Test` and `Booking`.

| Value | Label | Colour |
|-------|-------|--------|
| `scheduled` | Scheduled | grey |
| `booked` | Booked | blue |
| `complete` | Complete | green |
| `cancelled` | Cancelled | red |

Default: `scheduled`. The old `TestStatus` (Planned / In Progress / Completed) is removed.

### 1.2 New entity `Booking`
| Field | Type | Notes |
|-------|------|-------|
| `id` | int PK | |
| `title` | str, required | shown on the timeline bar |
| `unique_test_reference` | str \| null | **indexed**; optional link key, free text |
| `start_at` | datetime (tz-aware) | start date **and time** |
| `end_at` | datetime (tz-aware) | end date **and time** |
| `status` | EngagementStatus | default `scheduled` |
| `status_updated_at` | datetime | set whenever `status` changes; drives the sync "most-recent-wins" |
| `sort_order` | int | **global** row order (drag-reorder) |
| `created_at` | datetime | |

- **No FK to `Test`.** Linking is by `unique_test_reference` string match (auto-match).
- Multiple bookings may share a reference (a reschedule = a new booking).
- Each booking keeps its **own** status independently.

### 1.3 New entity `Scope`
| Field | Type | Notes |
|-------|------|-------|
| `id` | int PK | |
| `title` | str, required | friendly display name |
| `unique_test_reference` | str \| null | **indexed**; separate link key (Option 2) |
| `created_at` | datetime | |

- **No in-tool form fields** — the scoping detail lives entirely in attached files.
- Linked to test/booking/findings by `unique_test_reference` match.

### 1.4 New entity `ScopeAttachment`
Mirrors the existing `TestAttachment` pattern exactly (file stored under `ATTACHMENTS_DIR`, row holds `filename`, `content_type`, `size`, `scope_id` FK, `created_at`).

### 1.5 Changes to `Test`
- `status`: type changes from `TestStatus` → `EngagementStatus`, default `scheduled`.
- `scope` (free-text Text column): **removed** — superseded by the `Scope` entity.
- `unique_test_reference`: unchanged shape (nullable str, **not** enforced unique, stays editable) — but now **indexed** for matching.

---

## 2. Shared key + auto-match

`unique_test_reference` is the single linking key across **Findings, Tests, Scopes, Bookings**.

- **Not enforced unique, not required, stays editable** (per Tony).
- "Linked" = same non-null reference string. No FKs added for this; matching is done by querying on the string.
- Surfaced on every tab as the visible reference.
- Note/risk: because it's editable and not unique, links are best-effort. Two records with the same reference both match; a typo breaks the link. Acceptable for now; full integrity is a later concern.

---

## 3. Status sync rules (the tricky bit)

Goal (agreed): **test ↔ its latest booking stay in lockstep, two-way, last-write-wins; older/other bookings keep their own status.**

Implemented **server-side** in the update endpoints so it's consistent no matter which tab edits:

- **Booking status changes** → set `status_updated_at = now`. If a `Test` matches the reference, copy this status onto that test (and bump the test's `status_updated_at`).
- **Test status changes** → set its `status_updated_at = now`. If bookings match the reference, copy the status onto the **most-recently-updated** matching booking only (not all of them — so a cancelled original is left alone).
- A booking/test with **no match** just stores its own status.

This yields: the test and the "current" (latest-touched) booking always agree; reschedules/cancellations retain independent statuses.

---

## 4. API endpoints

### Bookings (`/bookings`)
- `GET /bookings` — list, ordered by `sort_order` (any logged-in user)
- `POST /bookings` — create (admin)
- `PATCH /bookings/{id}` — update; runs status-sync (admin)
- `DELETE /bookings/{id}` — delete (admin)
- `POST /bookings/reorder` — body: ordered list of booking ids → rewrites `sort_order` globally (admin)

### Scopes (`/scopes`) + attachments (mirror existing tests/attachments routers)
- `GET /scopes`, `POST /scopes` (admin), `PATCH /scopes/{id}` (admin), `DELETE /scopes/{id}` (admin)
- `POST /scopes/{id}/attachments` (admin), `GET /scopes/{id}/attachments`, `GET /scope-attachments/{id}` (download), `DELETE /scope-attachments/{id}` (admin)

### Tests
- `PATCH /tests/{id}` — existing; `status` now `EngagementStatus`; add status-sync.
- A small read helper to resolve "what links to reference X" (findings/test/scope/bookings) for the booking detail view — likely done client-side from the already-loaded lists rather than a new endpoint.

---

## 5. Frontend

### 5.1 `Bau.jsx` → Schedule (rewrite)
- **Period controls:** two date pickers (from / to). Default = **today − 9 months … today + 9 months** (18-month window). Persisted **per-user in localStorage** (keyed by user id). *(If you want it to follow you across devices, that's a small backend add — flagged as a decision below.)*
- **Weekly grid:** week columns across the period (~78 for 18 months), horizontally scrollable.
- **Rows:** one per booking, **drag-to-reorder** (persists globally via `/bookings/reorder`). Each row = title label + a status-coloured **bar** positioned/sized from `start_at`→`end_at`.
- **Colours:** grey/blue/green/red per status; a small legend.
- **Click a booking** → **detail drawer**: title, reference, exact start/end datetime, editable status (admin), and the linked test + its findings/scope (resolved by reference).
- **Add booking** (admin): form — title, reference (optional), start datetime, end datetime, status.

### 5.2 `Scopes.jsx` (rewrite)
- List of `Scope` records: title, reference, attachment list (upload/download/delete, admin), and a link to the matched test (by reference).
- **Add scope** (admin): title + reference, then upload files.

### 5.3 Tests tab
- Status dropdown now uses the 4 `EngagementStatus` values.
- Ensure `unique_test_reference` is visible/editable (already editable in the finding drawer; surface consistently).

### 5.4 `constants.js`
- Replace test-status constants with `ENGAGEMENT_STATUSES` + a `statusColor()` helper (grey/blue/green/red).
- Findings keep their own `FindingStatus` — unaffected.

---

## 6. Migration

Non-additive (enum change + dropped column + new tables). Since data isn't precious:
- Create tables: `bookings`, `scopes`, `scope_attachments`.
- `tests.status`: convert to the new enum, mapping any existing rows `Planned→scheduled`, `In Progress→booked`, `Completed→complete` (best-effort; data not important).
- Drop `tests.scope`.
- Add indexes on `unique_test_reference` for `tests`, `bookings`, `scopes`.

The existing additive `sync_missing_columns` startup helper covers new tables/columns; the enum swap + column drop need a dedicated one-time step in the same startup path.

---

## 7. RBAC (interim, until full model)
- **View:** any logged-in user.
- **Create / edit / delete / cancel / reorder** bookings and scopes: **admins only** (`require_admin`), same as tests today.

## 8. Out of scope (this build)
- **Bulk import** of bookings — deferred to a later pass.
- Full RBAC model.

## 9. Decisions (resolved)
1. **Per-user period persistence:** **localStorage** (per browser, no backend).
2. **One scope per reference:** **yes, one.** Reference→scope match resolves to a single scope. Not a hard DB constraint (references aren't enforced-unique), but the UI/logic treats it as one.
3. **Booking attachments:** **none** — only Scopes carry files.

## 10. Future enhancements (not this build)
- From the **booking detail drawer**, a control to **jump to the linked Scope** (and likely the linked Test/Findings too) by shared reference.
- Bulk import of bookings.
- Full RBAC model.
