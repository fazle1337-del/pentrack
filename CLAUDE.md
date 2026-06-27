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

**Status: planning + scaffold only. Not on `main`, not deployed.** A flag-gated
scaffold (one-directional "push a finding as an EV request") lives on branch
`easyvista-integration`, OFF by default (`easyvista_enabled`). Guide for the
scaffold as built: `docs/easyvista-integration.md`.

The intended feature is **bigger** than the scaffold: a stateful **two-way sync**
(assign → status → comments → close). Requirements are mostly settled; a few
answers are still pending **from the EV/Entra admin** before building.

- **Open questions to research:** tracked in the **Gitea wiki**, page
  *"EasyVista integration — open questions"* (`fazle1337/pentrack` wiki). Resolve
  those before writing Phase-A code.
- **Locked design decisions:** assignment is **group-based** (finding owner team =
  Entra group = EV assignee group); a single `pentrack` Entra identity is the
  requestor; **one ticket per finding**; assign is **admin-only**; EV is the
  **source of truth**, synced by **polling** (no EV webhooks); status mapping is
  **data-driven/configurable** for other tenants; comments are **cached**, visible
  to admins + the owning team, attributed to the real user via the action's
  `contact_*` field; poll intervals (open vs closed ticket) + on-demand refresh
  are **admin-tab adjustable**; the poller is **in-process** so it works in both
  Azure ACR and Umbrel.
- **EV API endpoints confirmed:** `POST /requests` (create), `GET /requests/{rfc}`
  (status as `STATUS_EN`/`STATUS_GUID`), `GET /requests/comment/{rfc}` (read
  comments), `POST /requests/{rfc}/actions` (post a comment as an *action*),
  close/suspend/reopen endpoints. **Identifier gotcha:** create returns an HREF
  ending in `REQUEST_ID`, but read/comment/close key off `rfc_number` — so capture
  `rfc_number` via a `GET` right after create and store *that* (the current
  scaffold stores the wrong id).
- **Proposed phasing:** A) assign + status (read-only sync) · B) comments (read) ·
  C) comments (write) · D) close-from-pentrack · plus admin "Integrations" tab +
  background poller.

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
