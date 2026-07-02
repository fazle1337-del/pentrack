# Pen Test Tracker

A self-hosted penetration-test findings tracker. Two user classes:

- **InfoSec admins** — manage tests, findings, risk ratings, and owner assignments.
- **Business team consumers** — view and update only findings assigned to them.

RBAC enforces this split. Runs on a self-hosted Umbrel instance (Raspberry Pi 5); Azure deployment is planned.

## Stack

- **Backend:** FastAPI (Python), SQLAlchemy, PostgreSQL
- **Frontend:** React + Vite, plain CSS matching Umbrel's dark aesthetic
- **Infra:** Docker Compose, multi-arch builds (arm64 + amd64)
- **Registry:** Docker Hub under `tonybooom`
- **Distribution:** Umbrel community app store, "tony" store, app ID `tony-pen-test-tracker`

## Roadmap

1. ✅ Backend API with RBAC
2. ✅ Frontend UI
3. ✅ CSV import (live, tested against real data)
4. ✅ BAU planning module (BAU schedule + shared reference key + scopes-as-forms)
5. ✅ Entra ID / OIDC SSO — live in prod (release 0.4.1)
6. ✅ Admin delete + cross-entity navigation — live in prod (release 0.5.0)
7. ✅ Runtime-configurable OIDC connection from the admin UI — release 0.6.0
   (issue #11 / PR #12). See "Runtime SSO config" below.
8. ✅ Security hardening — release 0.7.0 (issues #5–#9). See "Security audit"
   below for what shipped.
9. ✅ Teams admin UI (create / rename / delete) — release 0.7.0 (issue #13 /
   PR #17). See "Teams admin UI" below.
10. Dashboard ← **next up**
11. Azure portability
12. EasyVista (ITSM) two-way integration — **planning** (scaffold landed on
    branch `easyvista-integration`, behind `easyvista_enabled`). See
    "EasyVista integration" below.

**Current release: `0.7.0`** (images + Umbrel store). SSO is live on the
production instance `https://cheeseslice.duckdns.org`.

## Runtime SSO config (0.6.0) — issue #11

The OIDC/Entra connection (authority, client id, redirect, scopes, groups claim,
enable toggle, **and** the client secret) is editable from the admin **Access**
tab — no redeploy, no host-side secret file. Onboarding a tenant is now an admin
action, not an engineer task.

- **Resolver:** `core/oidc_config.get_oidc_config(db)` is the single source of
  truth — DB-over-env **per field**. Empty `oidc_settings` table == legacy
  env-only behaviour, so prod (which still sets `OIDC_*` env + the secret file in
  the `Tony-Umbrel` compose) keeps working unchanged until an admin overrides it.
- **Secret at rest:** stored encrypted in `oidc_settings.client_secret_enc`
  (Fernet, key derived from `jwt_secret` = `APP_SEED`; `core/crypto.py`).
  **Write-only** API (`GET/PUT /oidc-config`, admin-only): the GET returns only
  `client_secret_set`. ⚠️ Rotating `APP_SEED` makes the stored secret
  undecryptable → re-enter it in the Access tab (it also invalidates all
  sessions, so it's already a deliberate event).
- **No import-time snapshot:** `core/oidc.py` takes the resolved `OidcConfig` per
  request; discovery/JWKS caches keyed by authority; `reset_caches()` is called on
  save so the next login uses new config without a restart.
- Wiki: *"SSO setup — admin guide"* and *"SSO runtime config — technical
  reference"*.

## Security audit (2026-06-25) — RESOLVED in 0.7.0

Full application audit done (static review + live DAST against the running
Umbrel deployment). Report: `../Security Audit Reports/pentrack-2026-06-25-full-application-audit.md`
(sibling repo `Gitea/Security Audit Reports`). Verdict: **authz & injection
defense are strong** (no SQLi/XSS, RBAC enforced consistently, JWT in memory,
OIDC validated correctly, no mass-assignment); gaps were in session management
and hardening. All five issues (#5–#9) shipped in **0.7.0** (PRs #14–#17):

- **#5 (HIGH)** Token invalidation — `User.token_version` column + `tv` JWT claim
  checked in `core/deps.get_current_user`; `POST /auth/logout` bumps it (invalidates
  every prior token incl. the caller's). Frontend `logout()` calls it. Legacy/NULL
  values treated as 0 so existing sessions survive deploy. (PR #15)
- **#6 (MED)** Login rate-limiting — `slowapi` in-process limiter (`core/ratelimit.py`,
  no Redis), keyed on the left-most `X-Forwarded-For`; `/auth/login` → `LOGIN_RATE_LIMIT`
  (default `10/minute`), `LOGIN_RATE_LIMIT_ENABLED` toggle. (PR #16)
- **#7 (MED)** CORS — env-driven `CORS_ALLOW_ORIGINS` (default empty = none) and
  `allow_credentials=False` in `main.py`. (PR #14)
- **#8 (MED)** Security headers — `X-Frame-Options`, `nosniff`, `Referrer-Policy`,
  restrictive CSP in `frontend/nginx.conf` (HSTS left to the TLS edge). (PR #14)
- **#9 (MED)** API docs — `docs_url`/`redoc_url`/`openapi_url` gated behind
  `API_DOCS_ENABLED` (default `false`), so `/api/docs` is now 404 in prod. (PR #14)

**New env knobs (all safe defaults, no compose change required):**
`CORS_ALLOW_ORIGINS`, `API_DOCS_ENABLED`, `LOGIN_RATE_LIMIT`,
`LOGIN_RATE_LIMIT_ENABLED`. The backend image gained the `slowapi` dependency
(rebuild on deploy). Live DAST is reproducible from the Umbrel host against
`http://127.0.0.1:8099`.

## Teams admin UI (0.7.0) — issue #13

Teams (finding owner + IdP-group→role target) had no management UI — created only
via API/CSV, a dead end for admins. 0.7.0 adds `PATCH /teams/{id}` (rename, 409 on
dup) and `DELETE /teams/{id}` (admin), with delete **blocked (409 + reference
counts)** while a team is referenced by findings / users / `idp_role_maps` (no FK
cascade; nulling would lose ownership). Frontend: `createTeam`/`updateTeam`/
`deleteTeam` in `api.js` + a **Teams** manager in the admin **Access** tab
(`AccessControl.jsx`); `App.jsx` passes `onTeamsChanged` so the finding owner
picker and the Access-tab team dropdown refresh live. (PR #17)

### 0.5.0 — admin delete + cross-entity navigation (done, tested in prod)

- **Admin delete for tests & findings.** The backend `DELETE` endpoints
  (`routers/tests.py`, `routers/findings.py`, both admin-guarded) already
  existed; 0.5.0 wires up the missing UI: a row trash icon **and** a delete
  button in the detail drawer on both the Findings and Tests tabs, gated on
  `isAdmin` client-side and enforced admin server-side. Deleting a test
  cascades to its findings (`Test.findings` `cascade="all, delete-orphan"`),
  so the confirm shows the finding count. Both `DELETE` endpoints now enforce
  admin via the shared `require_admin` dependency (`delete_finding` previously
  used an inline `role` check) so the guard is visible in the route signature.
- **Cross-entity navigation by `unique_test_reference`.** New endpoint
  `GET /related?ref=<ref>` (`routers/related.py`) returns every test, finding,
  BAU booking and scope sharing that reference — **all** matches, since the ref
  is indexed but *not* unique — honouring the same finding RBAC as
  `GET /findings` (members see only findings they own). The shared
  `frontend/src/components/RelatedPanel.jsx` renders them as clickable chips in
  every drawer. Clicking one calls `App.jsx`'s lifted `navTo(type, id)`, which
  switches to the owning tab and auto-opens that entity's drawer (each tab has a
  nav-consume effect keyed on a `{type, id}` target). The link is a plain shared
  string — there is no hard FK between these four entities (see `models.py`
  notes on `Booking`/`Scope`).

## Deployment — read this before claiming anything is "deployed"

Umbrel serves the **Docker Hub images** pinned in the app's compose (in the Umbrel app-data / app-store repo), not this repo's source. Editing files here, or restarting the app in the Umbrel dashboard, changes nothing on its own.

Two images, built + pushed together under the **same semver tag** (e.g. `0.3.4`). **Bump the version on every change — never overwrite a published tag.**

- `tonybooom/pen-test-tracker-backend`  — build context `./backend`
- `tonybooom/pen-test-tracker-frontend` — build context `./frontend`

**1. Build + push (dev machine).** Images are multi-arch (the Pi is arm64). Once per machine/reboot, register QEMU + a container-driver builder:

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64
docker buildx create --name pentest-builder --driver docker-container --use   # only if missing
```

Then, bumping `X.Y.Z` each release:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t tonybooom/pen-test-tracker-backend:X.Y.Z  --push ./backend
docker buildx build --platform linux/amd64,linux/arm64 -t tonybooom/pen-test-tracker-frontend:X.Y.Z --push ./frontend
```

**2. Bump the Umbrel app-store repo — DON'T SKIP THIS.** Pushing images to Docker Hub does nothing until the store entry points at the new tag. The store entry is a **separate repo**: `Tony-Umbrel` (`http://192.168.1.118:8085/fazle1337/Tony-Umbrel`, branch `master`), local clone at `~/Gitea/Umbrel`, folder `tony-pen-test-tracker/`. Edit **both** files, then commit + push:

- `tony-pen-test-tracker/docker-compose.yml` — bump both `image:` tags (`web`/frontend and `api`/backend) to `X.Y.Z`.
- `tony-pen-test-tracker/umbrel-app.yml` — bump `version: "X.Y.Z"` (Umbrel keys "update available" off this) and refresh `releaseNotes`.

(That folder must contain ONLY those two files — never add source/scripts/Dockerfiles there.)

**3. Apply on Umbrel.** Update the app from the Umbrel dashboard (it reads the bumped store version), or on the Pi: `docker compose -f ~/umbrel/app-data/tony-pen-test-tracker/docker-compose.yml pull && ... up -d --force-recreate`. A dashboard *restart* won't pull *or* re-mount volumes/re-read env — only an update / **Stop+Start** / `--force-recreate` does. Then hard-refresh the browser: the frontend is nginx static; `/assets/*` JS/CSS are content-hashed and cached `immutable` for a year, but `index.html` is not, so a hard refresh pulls the new bundle. (There is **no** service worker, despite earlier notes here.)

**4. Verify.** Before calling it deployed, confirm the live container runs the new tag:

```bash
sudo docker inspect tony-pen-test-tracker_api_1 --format '{{.Config.Image}}'    # expect :X.Y.Z
docker buildx imagetools inspect tonybooom/pen-test-tracker-frontend:X.Y.Z | grep -i digest
```

## Umbrel-specific constraints

- The app's **host port is `8099`** (set in the store repo's `umbrel-app.yml` `port:`), moved off the default `8080` to avoid a clash with Pi-hole on the Umbrel server. The container-internal port stays `8080` (frontend nginx + `app_proxy` `APP_PORT`), namespaced inside the app network. Point any reverse proxy / 443 upstream at `8099`.
- No default-credentials popup: the `defaultUsername`/`defaultPassword` manifest fields are intentionally **omitted** (they trigger Umbrel's built-in credentials modal, which could block navigation behind an HTTPS proxy). First-login details live in the manifest `description` instead.
- Umbrel community apps don't handle `.env`-style secrets reliably. Use `${APP_SEED}` for the JWT secret and Postgres password, `${APP_PASSWORD}` for the seed admin password. Hardcode other env vars directly in the compose file.
- **App-store repo is strictly separate from the main project repo.** The `tony-pen-test-tracker/` folder must contain **only** `docker-compose.yml` and `umbrel-app.yml`. Watch for main-project files leaking into it — this has bitten us repeatedly.

## SSO (Microsoft Entra ID / OIDC)

Live in prod (0.4.1), **optional and off by default** (`oidc_enabled`). Full
operator guide is in the **README** (`## Single sign-on`); home-lab Keycloak test
harness is `docker-compose.sso-dev.yml` + `docs/sso-testing.md`.

- **Design:** the provider only authenticates; the backend validates the OIDC
  `id_token` then issues the app's **own JWT**, so all existing RBAC is unchanged.
  Code: `core/oidc.py`, `services/sso.py`, routes in `routers/auth.py`
  (`/auth/sso/login|callback`, `/auth/config`, `/auth/me`), admin CRUD in
  `routers/idp_maps.py`.
- **Groups → roles:** data-driven `idp_role_maps` table (`idp_group_id` = Entra
  group object-ID GUID → `admin`/`member` + optional team). Managed in the
  admin-only **Access** tab. `OIDC_BOOTSTRAP_ADMIN_GROUP`/`_MEMBER_GROUP` seed the
  two rows on first boot. A user whose groups map to nothing is denied (`no_role`).
- **Break-glass:** local username/password login is always available; SSO refuses
  to take over an email already owned by a local account (`local_account`).
- **Client secret — NEVER in git** (repos mirror to public GitHub, so the
  `Tony-Umbrel` compose holds only non-secret OIDC config). The secret is read from
  a file: `OIDC_CLIENT_SECRET_FILE=/data/secrets/oidc_client_secret`, bind-mounted
  from `${APP_DATA_DIR}/data/secrets` on the Pi.
- **⚠️ Bind-mount ordering gotcha (cost an hour):** the secret file must exist
  **before** the container is created, then the container **recreated** (Stop+Start
  / `--force-recreate`), *not* just restarted. Otherwise Docker shadow-mounts an
  empty `data/secrets` dir, the file is invisible inside the container, the secret
  reads empty, and SSO fails with `login_failed`. Verify with
  `sudo docker exec tony-pen-test-tracker_api_1 cat /data/secrets/oidc_client_secret`.
  Rotate by overwriting the file + `docker restart` the api container.

## EasyVista (ITSM) integration — planning

**Status: Phase A (assign + status) and Phase B (comments, read) complete
(backend + frontend), landed on `main` (2026-07-01/02), flag OFF, never
deployed active.** The original flag-gated scaffold (PR #10, one-directional
"push a finding as an EV request") plus everything below (corrections,
assignment, status sync, the poller, comments, and the UI) are all live in
`main` behind `easyvista_enabled` (default `False` — `POST
/itsm/findings/{id}/push` 404s until an admin turns it on). Guide:
`docs/easyvista-integration.md`.

The intended feature is **bigger** than Phase A/B: a stateful **two-way sync**
(assign → status → comments → close). All design questions are resolved
except one (Q5, below).

- **Open questions:** tracked in the **Gitea wiki**, page *"EasyVista
  integration — open questions"* (`fazle1337/pentrack` wiki). Q1–Q4 resolved
  2026-07-01. **Only Q5 remains:** the tenant's actual `STATUS_EN`/
  `STATUS_GUID` status list — not a hard blocker (closed/open is `END_DATE_UT`
  being set, not a status enum value), just needed to seed the admin-facing
  `status → {open|closed}` display map. Follow-up sent to the technician.
- **Q3/Q4 resolved:** raising a ticket is **admin-only** in all cases; once
  raised, the assigned owner team can add comments. All three transitions
  (close/reopen/suspend) are supported by the EV service account — no
  API-side restriction to design around. Token rotation: the **admin**
  requests the technician rotate the bearer token, then re-enters it via
  `PUT /easyvista-config` — same pattern as the Entra/OIDC client secret (see
  "Runtime SSO config" above).
- **Entra groups ≠ EV groups (corrected + built).** EV has its own
  `AM_GROUP`/`AM_EMPLOYEE`/`AM_EMPLGROUP` tables with no shared namespace with
  Entra; the only cross-system join key for *people* is EV's `AM_EMPLOYEE.
  IDENTIFICATION` = the Entra staff number (email ↔ `AM_EMPLOYEE.LOGIN` as
  fallback). **Schema landed:** `Team.ev_group_id`, `User.staff_number`,
  `User.ev_employee_id` (all unique, nullable — `models.py`), additive to, not
  a replacement for, the existing Entra-group-driven `idp_role_maps` (which
  still governs pentrack RBAC; the new columns are purely for EV ticket
  routing). `ev_group_id` is consumed by assignment (see below) and settable
  from the frontend **Access** tab's Teams manager (rename row gained an "EV
  group id" field + a "Load EV groups…" picker sourced from
  `GET /itsm/groups`); `staff_number`/`ev_employee_id` aren't consumed or
  UI-editable yet — needed starting Phase C (comment attribution).
  **Skipped deliberately:** the
  technician also suggested a Team↔User EV-membership junction table
  (mirroring `AM_EMPLGROUP`) — not built, since nothing in Phases A–D
  consumes it; add it if a real need for multi-group EV membership tracking
  shows up.
- **Auth is a bearer token, not HTTP Basic (corrected + built).** EV uses a
  bearer token from a managed-identity account, expiring on a tenant-set
  policy capped at yearly, no auto-refresh. `services/easyvista.py` now sends
  `Authorization: Bearer <token>`; the token resolves DB-over-env via
  `core/easyvista_config.py`, stored encrypted at rest
  (`EasyVistaSettings.bearer_token_enc`, a **distinct Fernet KDF context**
  from the OIDC secret — `core/crypto.py`'s `EASYVISTA_CONTEXT`) and editable
  via the new admin-only `PUT/GET /easyvista-config`
  (`routers/easyvista_config.py`), now with a frontend panel too (the new
  **Integrations** tab, `Integrations.jsx` — write-only like the OIDC secret,
  same "leave blank to keep" pattern). The old
  `easyvista_login`/`easyvista_password`/`easyvista_password_file` settings
  and `EASYVISTA_PASSWORD_FILE` deploy step are gone; env fallback is now
  `EASYVISTA_BEARER_TOKEN`/`EASYVISTA_BEARER_TOKEN_FILE` (pre-admin-UI
  bootstrap only — admin UI always wins once set). No expiry reminder built
  yet (still needed).
- **`rfc_number` identifier bug fixed.** `create_request` now does a
  follow-up `GET /requests/{REQUEST_ID}` right after create to resolve and
  store `rfc_number` (falling back to the raw `REQUEST_ID` if that lookup
  fails, so a successfully created ticket's reference is never lost) — this
  assumption (`GET /requests/{id}` accepts `REQUEST_ID` as well as
  `rfc_number`) is unverified against a live tenant, same caveat the auth
  mechanism had before it was confirmed.
- **New read-only EV client methods landed:** `list_groups`, `get_group`,
  `list_group_employees`, `list_employee_groups` in `services/easyvista.py`
  (`GET /groups`, `/groups/{id}`, `/groups/{id}/employees`,
  `/employees/{id}/groups`) — `GET /itsm/groups` (admin-only) exposes
  `list_groups` for the future Integrations-tab UI; the rest aren't wired to a
  route yet.
- **Assignment logic landed.** `PATCH /teams/{id}` now accepts `ev_group_id`
  (omit to leave unchanged — so plain renames from the existing Access-tab UI
  can't accidentally wipe it; `""` clears it; enforces uniqueness). Pushing a
  finding (`POST /itsm/findings/{id}/push`) now stamps the owning team's
  `ev_group_id` onto the EV request as `group_id`, and is **gated**: 409 if the
  finding has no owning team, 409 if the team has no `ev_group_id` mapped yet
  — no ticket is ever raised without an assignee group.
- **Bug found + fixed during manual end-to-end testing (real Postgres + the
  local stub server, not just mocked tests):** `create_request` was closing
  its own `httpx.Client` right after the POST, then reusing that closed client
  for the `rfc_number` follow-up GET — broke every real push (every unit test
  had injected its own client, masking it, since `owns_client` is only `True`
  in the real code path). Fixed by keeping the client open across both calls;
  regression-tested by making the module construct its own client against a
  mock transport (no `client=` kwarg passed), which is the path that broke.
  Same end-to-end pass also caught the local stub server only indexing
  tickets by numeric `REQUEST_ID`, not `rfc_number` — fixed in
  `tests/easyvista_stub.py` (a test-double gap, not a production bug).
- **Status sync landed — both on-demand and background polling.**
  `services/easyvista.get_request_status(rfc_number, db)` does
  `GET /requests/{rfc}`, returning the raw `STATUS_EN`/`STATUS_GUID` label
  plus a `closed` bool derived from `END_DATE_UT` being present (unverified
  field-name assumption, same caveat as the identifier gotcha — tries a few
  casings, `None` if absent rather than guessing). `POST
  /itsm/findings/{id}/refresh` (admin-only; 409 if the finding was never
  pushed) is the on-demand path; caches the result on three new `Finding`
  columns (`itsm_status_label`, `itsm_closed`, `itsm_synced_at` —
  system-managed, `FindingOut`-only, not on `FindingCreate`/`FindingUpdate`).
  The finding drawer (`Findings.jsx`) now shows a **"Push to EasyVista"**
  button when there's no `itsm_reference` yet, and once pushed, an
  open/closed badge + the raw status label + last-synced time plus a
  **"Refresh status"** button — admin-only, only rendered when
  `GET /itsm/config` reports `itsm_enabled`. The 409 gating messages (no
  owning team / team has no EV group) surface directly as the drawer's error
  text.
- **Background poller landed** (`services/easyvista_poller.py`, an asyncio
  task started/cancelled in `main.py`'s `lifespan`, ticking every
  `easyvista_poll_tick_seconds`, running the sync `poll_once(db)` via
  `asyncio.to_thread` so it never blocks the API event loop). Only polls
  findings pentrack already knows about (`itsm_reference` set) — does **not**
  poll EV globally by ticket category to discover unknown tickets (the
  technician's stretch suggestion; needs a "list by category" EV endpoint
  that isn't confirmed). Per-finding due-date logic implements the locked
  two-interval decision: open findings re-poll on `poll_open_interval_seconds`
  (default daily), closed ones on `poll_closed_interval_seconds` (default
  weekly) but stop being polled at all once `poll_closed_lookback_days`
  (default 365) has passed since last sync — matches the technician's
  suggested defaults. All four settings (`poll_enabled` + the three
  intervals) are **admin-tab adjustable**: DB-over-env on `EasyVistaSettings`,
  same non-secret-plain-storage pattern as the bearer token is
  encrypted-secret storage, both via `PUT/GET /easyvista-config`. Verified
  end-to-end against real Postgres + the local stub with a 2-second tick
  interval: pushed a finding, waited with **no manual `/refresh` call**, and
  confirmed the background task picked it up and cached its status
  automatically.
- **Locked design decisions:** assignment is **group-based**
  but via a **new explicit EV-group mapping**, not the Entra group (see
  correction above); a single `pentrack` Entra identity is the requestor;
  **one ticket per finding**; assign is **admin-only**; EV is the **source of
  truth**, synced by **polling** (no EV webhooks — technician suggests daily
  polling of open tickets in the pentest category, closed-ticket polling bounded
  to ~1 year back, and on-demand polling of actions per ticket); status mapping
  is **data-driven/configurable**, with the closed signal being `END_DATE_UT`
  (ticket *or* action level) rather than a status enum value; comments are
  **cached** — confirmed a "comment" = an EV **action** of a specific
  `AM_ACTION_TYPE` (the ticket description itself is the first comment) —
  visible to admins + the owning team, attributed to the real user via the
  action's `contact_*` field; poll intervals (open vs closed ticket) + on-demand
  refresh are **admin-tab adjustable**; the poller is **in-process** so it works
  in both Azure ACR and Umbrel. Ownership/ticket-closing state lives at the
  **Action** level, not just the ticket level (many actions per `SD_REQUEST`) —
  open actions must be queried separately from ticket status.
- **EV API endpoints confirmed:** `POST /requests` (create), `GET /requests/{rfc}`
  (status as `STATUS_EN`/`STATUS_GUID`), `GET /requests/comment/{rfc}` (read
  comments — **consumed, Phase B**), `POST /requests/{rfc}/actions` (post a
  comment as an *action* — Phase C, not built), close/suspend/reopen endpoints
  (Phase D, not built) — group/employee endpoints are implemented, see above.
- **Comments (Phase B, 2026-07-02) landed — backend and frontend, read-only.**
  New `FindingItsmComment` cache table (`models.py`) and
  `easyvista.get_request_comments(rfc_number, db)` (`GET
  /requests/comment/{rfc}`, same defensive-field-parsing pattern as
  `get_request_status` — casing unverified against a live tenant, degrades to
  `None` rather than guessing). Two routes on `routers/itsm.py`: `POST
  /itsm/findings/{id}/comments/sync` (fetches from EV, **replaces** the
  finding's cached rows — EV is the source of truth, so no diff/upsert) and
  `GET /itsm/findings/{id}/comments` (cache only, no EV call). Both are gated
  by a new shared `core.deps.can_access_finding` (admin, or owner user/team) —
  lifted out of `routers/findings.py`'s previously-private `_can_access` so
  `routers/itsm.py` and `routers/attachments.py` can share the exact same
  visibility rule instead of redefining it, matching the wiki's "comments
  visible to admins + owning team" decision (unlike push/refresh, which stay
  admin-only). **Never background-polled** — comments are on-demand only per
  the wiki's polling design ("actions are the expensive/chatty part"), so
  `services/easyvista_poller.py` is untouched. Frontend: a **Comments**
  section in the finding drawer (`Findings.jsx`), shown to admins + the
  owning team (not admin-gated like the status block above it) once a finding
  is pushed, with a "Sync comments" button and the cached thread (author,
  action type, timestamp, body) — `App.jsx` now passes `me` down to
  `Findings`/`FindingDrawer` so the drawer can check the viewer's `team_id`
  against the finding's owning team. Author attribution is a display string
  from the action's `contact_*` field only — no join to a pentrack `User` yet
  (`staff_number`/`ev_employee_id` are still unconsumed; that's Phase C,
  needed for comment *writing* so a posted comment can be attributed to the
  real user instead of the shared `pentrack` service identity).
- **Proposed phasing:** A) assign + status — **fully landed** (see above) ·
  B) comments (read) — **fully landed, backend and frontend** (see above) ·
  C) comments (write) · D) close-from-pentrack.

## Database migrations

Additive schema changes must be **idempotent** to avoid data loss on existing deployments. The startup migration `sync_missing_columns` handles additive column changes on existing databases without data loss. Follow that pattern for new additive changes.

## Getting the initial admin login

The local seed admin is the **break-glass** account (works even if SSO/the IdP is
down); SSO is the primary day-to-day login.

- Username: `admin@example.com`
- Password: `sudo docker exec tony-pen-test-tracker_api_1 printenv SEED_ADMIN_PASSWORD`

## Working conventions

- State assumptions before writing code. Ask when ambiguous.
- Prefer minimal, simple solutions. No unnecessary abstractions.
- Make surgical changes only — touch nothing outside the task scope.
- End every task by verifying it meets the stated success criteria (for deploy tasks, that means the `CACHE_NAME` check above).

## Known fixed bugs (for context)

`itsm_reference` field silently dropped on save; missing attachment deletion endpoint/UI; vendor recommendation was display-only and hidden when empty; Additional Information and Date Logged in Resolver missing from the finding drawer. All resolved.
