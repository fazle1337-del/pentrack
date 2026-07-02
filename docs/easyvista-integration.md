# EasyVista (ITSM) integration

Pushes a finding into **EasyVista Service Manager** as a request/incident and
stores the returned reference on the finding's `itsm_reference`. **Optional and
OFF by default** (`easyvista_enabled`) — it ships dark and is validated against a
real tenant later, mirroring the SSO rollout. **Phase A is fully built, backend
and frontend** (schema, auth, group/employee client methods,
assignment-on-push, on-demand status refresh, the background poller, and the
admin UI for all of it); see the Gitea wiki page *"EasyVista integration —
open questions"* for the full design and phasing.

It was built **without a live EasyVista tenant**: the code targets the
documented [create-a-request](https://docs.easyvista.com/docs/rest-api-create-an-incident-request)
REST contract, and is exercised with a mock and a local stub (below). One thing
still needs confirming against a real tenant — see
[Open questions](#open-questions-confirm-against-a-real-tenant).

## How it works

```
POST {host}/api/v1/{account}/requests   (Bearer token auth)
  -> 201 {"HREF": ".../requests/{id}"}   # trailing id is the REQUEST_ID
GET  {host}/api/v1/{account}/requests/{REQUEST_ID}
  -> 200 {"rfc_number": "..."}           # rfc_number is stored as itsm_reference
```

1. The frontend can show a **Push to EasyVista** action when `GET /itsm/config`
   reports `itsm_enabled: true`.
2. An admin calls `POST /itsm/findings/{id}/push` (admin-only; 404s when the flag
   is off). Pushing is an **explicit per-finding action**, never automatic on
   finding create — so nothing leaves the app until an operator opts in.
   **Gated on assignment** (EV routing is group-based): `409` if the finding
   has no owning team, `409` if the owning team has no `ev_group_id` mapped
   yet (set via `PATCH /teams/{id}`) — no ticket is ever raised without an
   assignee group.
3. The backend maps the finding to a request body — including the owning
   team's `ev_group_id` as `group_id` — POSTs it with a bearer token, parses
   the `HREF`'s `REQUEST_ID`, then does a follow-up `GET` to resolve the
   `rfc_number` — **that** is what's stored on `finding.itsm_reference`, not the
   raw `REQUEST_ID` (the "identifier gotcha": create returns `REQUEST_ID`, but
   read/comment/close key off `rfc_number`). If the follow-up `GET` fails, the
   `REQUEST_ID` is stored instead rather than losing the reference to a ticket
   that was already created.
4. Errors are mapped: `401` → bad/expired bearer token, `406` → unknown
   requestor/recipient domain, anything else → `502` to the caller.
5. **Status sync is both on-demand and automatic.** An admin can call
   `POST /itsm/findings/{id}/refresh` (admin-only; 409 if the finding hasn't
   been pushed yet) any time; it does `GET /requests/{rfc_number}` and caches
   the raw `STATUS_EN` label plus a `closed` bool onto the finding
   (`itsm_status_label`, `itsm_closed`, `itsm_synced_at` — system-managed,
   only ever set by this refresh path). `closed` comes from `END_DATE_UT`
   being present in the response, **not** a status-label match — that's the
   authoritative signal per the wiki, and the field-name assumption is
   unverified against a live tenant (same caveat as the identifier gotcha).
   Separately, an **in-process background poller**
   (`app/services/easyvista_poller.py`) does the same refresh automatically
   for every pushed finding, on a schedule: open findings every
   `poll_open_interval_seconds` (default daily), closed ones every
   `poll_closed_interval_seconds` (default weekly) but never again once
   `poll_closed_lookback_days` (default 365) has passed since last sync. It's
   an asyncio task started in `main.py`'s `lifespan`, ticking every
   `poll_tick_seconds` (default 300s) and running the actual poll in a thread
   so it never blocks API requests. `poll_enabled` and the three intervals
   are admin-tab adjustable (DB-over-env, `PUT/GET /easyvista-config`) — it
   only polls findings pentrack already knows about; it does **not** query EV
   globally by ticket category to discover ones it doesn't (the technician's
   stretch suggestion — needs an unconfirmed "list by category" EV endpoint).

The whole EasyVista surface lives in **one module**, `app/services/easyvista.py`
— that isolation *is* the adapter boundary. Retarget a different ITSM by swapping
that file; no abstract base class until a second backend exists. The same
module also has read-only client methods for groups/employees
(`list_groups`, `get_group`, `list_group_employees`, `list_employee_groups`),
used to populate the EV-id mapping columns below — not yet wired to any admin
UI (that lands with the "Integrations" tab in a later slice).

| Concern | Location |
|---|---|
| Mapping + REST client + persist | `backend/app/services/easyvista.py` |
| Background poller (due-date logic + one pass) | `backend/app/services/easyvista_poller.py` |
| Poller asyncio task (start/stop in `lifespan`) | `backend/app/main.py` |
| Routes (`/itsm/config`, push, refresh, `/itsm/groups`) | `backend/app/routers/itsm.py` |
| `Team.ev_group_id` admin CRUD (`PATCH /teams/{id}`) | `backend/app/routers/teams_users.py` |
| Bearer-token + poll-settings admin CRUD (`/easyvista-config`) | `backend/app/routers/easyvista_config.py` |
| Bearer-token + poll-settings DB-over-env resolver | `backend/app/core/easyvista_config.py` |
| Settings (env fallback only) | `backend/app/core/config.py` |
| Mock tests (no tenant) | `backend/tests/test_easyvista.py` |
| Push/refresh-gating + assignment router tests | `backend/tests/test_itsm_router.py` |
| Poller due-date logic + one-pass tests | `backend/tests/test_easyvista_poller.py` |
| Bearer-token/poll-settings resolver/crypto tests | `backend/tests/test_easyvista_config.py`, `test_easyvista_config_router.py` |
| Local stub server | `backend/tests/easyvista_stub.py` |
| Admin "Integrations" tab (token + poll settings) | `frontend/src/components/Integrations.jsx` |
| `Team.ev_group_id` editing + "Load EV groups…" picker | `frontend/src/components/AccessControl.jsx` (`TeamsManager`) |
| Push / Refresh buttons + status display | `frontend/src/components/Findings.jsx` (`FindingDrawer`) |
| Frontend API client methods | `frontend/src/api.js` |

## Frontend

- **Integrations tab** (admin-only, next to Access): bearer token (write-only,
  same "leave blank to keep" pattern as the OIDC secret) + the four poll
  settings. Shows a note if `easyvista_enabled` is off at the deployment
  level — settings can still be saved, they just won't do anything yet.
- **Access tab → Teams manager**: renaming a team now also shows/edits
  `ev_group_id`, with a "Load EV groups…" button that fetches
  `GET /itsm/groups` and turns into a `<select>` so an admin doesn't have to
  know the raw EV group id by heart. Only shown when `itsm_enabled`.
- **Finding drawer**: a "Push to EasyVista" button when there's no
  `itsm_reference` yet; once pushed, an open/closed badge + the raw
  `STATUS_EN` label + last-synced time, plus a "Refresh status" button. Both
  admin-only, only rendered when `itsm_enabled`. The 409 gating messages (no
  owning team / team has no EV group) surface as the drawer's normal error
  text.

Verified in a real browser (Playwright against a live dev stack — backend +
the local stub + Vite), not just curl/pytest: logged in, saved Integrations
settings, mapped a team's `ev_group_id` via the picker, pushed a finding
(confirmed `itsm_reference` resolves to the `rfc_number`, not the raw
`REQUEST_ID`), refreshed its status (confirmed the badge/label/timestamp),
and hit the "no owning team" 409 to confirm the error renders cleanly.

## Schema (2026-07-01 — Entra groups ≠ EV groups)

The EV technician confirmed Entra groups and EV groups are **separate
namespaces** (no name/mail shortcut), so ticket routing needs its own mapping,
additive to (not a replacement for) `idp_role_maps`:

- `Team.ev_group_id` (unique, nullable) — an EV `GROUP_ID`, populated by an
  admin from `GET /groups`.
- `User.staff_number` (unique, nullable) — the person's Entra staff number,
  matching EV's `AM_EMPLOYEE.IDENTIFICATION`.
- `User.ev_employee_id` (unique, nullable) — EV's own `EMPLOYEE_ID`, resolved
  via `GET /employees` (or email ↔ `AM_EMPLOYEE.LOGIN` as a fallback).

`Team.ev_group_id` is now consumed — it's stamped onto every pushed request as
`group_id`, and pushing is blocked (409) until it's set (see "How it works").
`staff_number`/`ev_employee_id` aren't consumed yet — needed starting Phase C
(comment attribution via the action's `contact_*` field). They exist now so an
admin can start populating them ahead of that UI landing. Existing
databases get the columns via `sync_missing_columns` and the `UNIQUE`
constraint via a dedicated `sync_easyvista_unique_indexes()` step in
`main.py` (`ALTER TABLE ADD COLUMN` alone doesn't carry constraints over) —
new deployments get both from `create_all`.

## Configuration

**Auth (2026-07-01 correction):** EV uses a **bearer token** tied to a managed
identity, not HTTP Basic — the scaffold's original assumption was wrong. The
token is stored **encrypted at rest**, admin-tab editable via
`PUT/GET /easyvista-config` (mirrors the OIDC client secret's
`client_secret_enc` pattern, `app/core/crypto.py` — a distinct KDF context so
the two secrets' derived keys can never collide). No frontend UI yet; the
env/file fields below are the pre-admin-UI fallback (DB always wins when set),
same relationship `oidc_client_secret_file` has to the OIDC admin UI.

Everything else (host, account, catalog, requestor mail) stays
deployment-level env, like before — only the token has a rotation lifecycle
an admin needs to manage without a redeploy.

| Setting | Env var | Secret? | Goes where |
|---|---|---|---|
| Enable the integration | `EASYVISTA_ENABLED=true` | no | compose |
| Host | `EASYVISTA_HOST=https://<account>.easyvista.com` | no | compose |
| Account / path segment | `EASYVISTA_ACCOUNT` | no | compose |
| **Bearer token** | admin UI (`PUT /easyvista-config`), or `EASYVISTA_BEARER_TOKEN_FILE=/data/secrets/easyvista_bearer_token` | **yes** | **admin UI (preferred) or file on the Pi** |
| Catalog GUID (request subject) | `EASYVISTA_CATALOG_GUID` | no | compose |
| Requestor/recipient mailbox | `EASYVISTA_REQUESTOR_MAIL` | no | compose |
| HTTP timeout (default 30s) | `EASYVISTA_TIMEOUT_SECONDS` | no | compose |
| Background poller on/off (default off) | `EASYVISTA_POLL_ENABLED`, or admin UI | no | compose or admin UI |
| Poller wake-up cadence (default 300s) | `EASYVISTA_POLL_TICK_SECONDS` | no | compose |
| Open-finding poll interval (default 86400s = daily) | `EASYVISTA_POLL_OPEN_INTERVAL_SECONDS`, or admin UI | no | compose or admin UI |
| Closed-finding poll interval (default 604800s = weekly) | `EASYVISTA_POLL_CLOSED_INTERVAL_SECONDS`, or admin UI | no | compose or admin UI |
| Stop re-polling closed tickets after (default 365 days) | `EASYVISTA_POLL_CLOSED_LOOKBACK_DAYS`, or admin UI | no | compose or admin UI |

> One of `EASYVISTA_CATALOG_GUID` / `EASYVISTA_CATALOG_CODE` is **required** by
> the API (GUID preferred). Its value comes from the tenant's EV catalogue.

**Rotation:** when the technician rotates the token in EV, an admin re-enters
it via `PUT /easyvista-config` — no host-side file handoff, no redeploy.

**Poller:** `EASYVISTA_POLL_TICK_SECONDS` is how often the background loop
*wakes up to check what's due*, not the poll interval itself — the four
poll-behavior settings (enabled + the three intervals) can be changed live via
`PUT /easyvista-config` without a restart, since `poll_once()` re-resolves
them (DB-over-env) on every tick.

## Deploying when creds arrive

1. **Build + push** new images under a fresh semver tag (never overwrite a
   published tag — see the root `CLAUDE.md` deploy section).
2. **Edit the `Tony-Umbrel` compose** (`api`/backend service): add the non-secret
   `EASYVISTA_*` env vars above; bump the version in both store files.
3. **Set the bearer token via the admin UI** once the app is up (preferred —
   no file handoff). If you need it available before first login, the file
   pattern still works: reuse the OIDC secret's existing
   `${APP_DATA_DIR}/data/secrets` bind-mount and add
   `${APP_DATA_DIR}/data/secrets/easyvista_bearer_token`, then point
   `EASYVISTA_BEARER_TOKEN_FILE` at it. Pointing at a path that isn't already
   mounted hits the bind-mount ordering gotcha (the file must exist *before*
   the container is created, then the container recreated).
4. **Recreate the container** (Stop+Start or `--force-recreate`) if you changed
   env/compose. A plain *restart* does **not** re-read env vars. This also
   pulls the new image tag.
5. **Verify:**
   ```bash
   curl -s http://127.0.0.1:8099/api/itsm/config        # {"itsm_enabled": true}
   ```
   then push one real finding to confirm auth + the `catalog_guid`.

## Testing without a tenant

### Mock tests (zero setup — fake EasyVista is in-memory)

`pytest` drives the service through an `httpx.MockTransport` that returns the
documented responses. No server, no network, no creds.

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

### Local stub (fake EasyVista runs on your laptop)

`tests/easyvista_stub.py` is a tiny server that *pretends to be EasyVista* on
`127.0.0.1:9001` — create-request (with the rfc_number follow-up `GET`) plus
the group/employee read endpoints. Point the backend's `EASYVISTA_HOST` at it
(not at easyvista.com) and the full push path runs end-to-end against your
own stub.

```bash
# terminal 1 — run the stub
cd backend && uvicorn tests.easyvista_stub:app --port 9001

# terminal 2 — configure the backend to use the stub, then start the app
export EASYVISTA_ENABLED=true
export EASYVISTA_HOST=http://127.0.0.1:9001
export EASYVISTA_ACCOUNT=50012
export EASYVISTA_CATALOG_GUID=GUID-LOCAL
export EASYVISTA_REQUESTOR_MAIL=pentrack@local.test
export EASYVISTA_BEARER_TOKEN=stub-token   # plain env var ok locally; file/admin-UI pattern is prod-only
# ... start the app, then POST /itsm/findings/{id}/push as an admin,
# then POST /itsm/findings/{id}/refresh to sync its status back
```

Set `STUB_STATUS=401` (or `406`) in the stub's env to exercise the failure
paths, or `STUB_CLOSED=1` to make every `refresh` see the ticket as closed
(`END_DATE_UT` set, `STATUS_EN: "Closed"`) instead of open. The stub indexes
each created ticket under **both** its numeric `REQUEST_ID` and its
`rfc_number` — a real gap found via manual end-to-end testing (the stub
originally only indexed by `REQUEST_ID`, so `refresh`'s `rfc_number`-keyed
lookup 404'd even though the real production code was correct).

## Open questions (confirm against a real tenant)

1. **`rfc_number` lookup.** `_fetch_rfc_number` in `app/services/easyvista.py`
   assumes `GET /requests/{id}` accepts the create response's `REQUEST_ID` (not
   just `rfc_number`) as the path parameter, and that the response body has an
   `rfc_number` field. Unverified against a live tenant — confirm and adjust if
   wrong.
2. **Catalogue + risk mapping.** The tenant-specific `catalog_guid`, and any
   risk-rating → EV urgency/severity ID mapping, are deliberately left out rather
   than guessed. Wire them once a real catalogue is known.
3. **Status list (wiki Q5, still open).** The tenant's `STATUS_EN`/`STATUS_GUID`
   values aren't needed for correctness — closed/open is `END_DATE_UT` being
   set, not a status enum — but are still useful for the admin-configurable
   display map. See the wiki page.
4. **Assignment field is hardcoded to `group_id` — to investigate later.**
   `_build_body` in `app/services/easyvista.py` always stamps the EV group as
   `group_id`. The wiki technician's Q2 answer said EV's assignment fields
   are `group_id` / `group_mail` / `group_name` — i.e. **which one a given
   tenant's catalog/workflow expects is a real per-customer difference**, not
   an unconfirmed detail of this one tenant. Since pentrack ships as an
   installable Umbrel app (other self-hosters, each with their own EV
   tenant), this is worth generalizing eventually: a setting for which field
   name to use, defaulting to `group_id`. Deliberately **not done yet** —
   flagged during a design discussion (2026-07-02) and deferred rather than
   built speculatively.
