# PenTrack — Backend (Phase 1)

Findings & remediation tracker. Phase 1 = core API vertical slice.

## Run (Docker — Pi5 / Azure-portable)

```bash
# from repo root
JWT_SECRET=$(openssl rand -hex 32) \
SEED_ADMIN_EMAIL=admin@yourco.com \
SEED_ADMIN_PASSWORD='a-strong-password' \
docker compose up --build
```

API: http://localhost:8000  ·  Interactive docs: http://localhost:8000/docs

On first boot, a single InfoSec **admin** user is seeded from the env vars
above (only if the users table is empty).

## Run (local, no Docker)

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL="sqlite:///./pentrack.db"   # or a Postgres URL
export ATTACHMENTS_DIR="./attachments"
uvicorn app.main:app --reload
```

## Auth

- `POST /auth/login` (form: `username`=email, `password`) → JWT bearer token.
- Send `Authorization: Bearer <token>` on all other requests.
- Local accounts plus optional Microsoft Entra ID / OIDC SSO (see below).

## Single sign-on (Microsoft Entra ID / OIDC)

SSO is **optional and off by default**. The provider only authenticates; the app
then issues its own JWT, so all RBAC is unchanged. Identity-provider **groups map
to app roles**, and **local login always remains as a break-glass path** (SSO will
not take over an email already owned by a local account). For the home-lab Keycloak
test harness, see [`docs/sso-testing.md`](docs/sso-testing.md).

### 1. Register the app in Entra

1. **App registrations → New registration.** Single-tenant. Redirect URI (platform
   **Web**): `https://<your-host>/api/auth/sso/callback` — exact match, no trailing slash.
2. From **Overview**, copy the **Application (client) ID** and **Directory (tenant) ID**.
3. **Certificates & secrets → New client secret** → copy the `Value` (shown once).
4. **Token configuration → Add groups claim → Security groups** (added to the ID token).
5. **Groups → New group** (Security) for e.g. `PenTrack-Admins` / `PenTrack-Members`;
   copy each group's **Object Id** (GUID).

### 2. Configure the app

Set these on the `api` service (non-secret values only — safe to commit):

| Env var | Value |
|---|---|
| `OIDC_ENABLED` | `true` |
| `OIDC_AUTHORITY` | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| `OIDC_CLIENT_ID` | application (client) ID |
| `OIDC_REDIRECT_URI` | `https://<your-host>/api/auth/sso/callback` |
| `OIDC_POST_LOGIN_REDIRECT` | `https://<your-host>/` |
| `OIDC_GROUPS_CLAIM` | `groups` |
| `OIDC_BOOTSTRAP_ADMIN_GROUP` | admin group GUID *(optional: auto-seeds the mapping on first boot)* |
| `OIDC_BOOTSTRAP_MEMBER_GROUP` | member group GUID *(optional)* |

### 3. Provide the client secret without committing it

The secret is read from a **file**, never an env var in git. Set the path and mount
a file the app reads at startup (file contents win over `OIDC_CLIENT_SECRET`):

```yaml
environment:
  OIDC_CLIENT_SECRET_FILE: /data/secrets/oidc_client_secret
volumes:
  - ${APP_DATA_DIR}/data/secrets:/data/secrets:ro
```

Create the secret on the host. It lives in the app's persistent data dir, so it
survives app updates; rotate by overwriting the file.

```bash
sudo mkdir -p ~/umbrel/app-data/tony-pen-test-tracker/data/secrets
printf '%s' 'YOUR_ENTRA_SECRET' | sudo tee \
  ~/umbrel/app-data/tony-pen-test-tracker/data/secrets/oidc_client_secret >/dev/null
```

> **⚠️ Order matters — create the directory + file *before* the container is
> created, then recreate the container.** If the `data/secrets` dir doesn't exist
> when the app first starts, Docker auto-creates an empty one and bind-mounts
> *that*; a file you add afterwards lands in a different directory the running
> container can't see (`cat … : No such file or directory`), and the secret reads
> as empty so SSO fails with `login_failed`. A plain **restart won't fix it** — the
> stale mount persists. After the file exists, **recreate** the container (Umbrel
> UI: **Stop** then **Start**, *not* Restart — or `docker compose up -d
> --force-recreate`) so it binds the real directory and reads the secret at startup.

**Verify the container can read it** before testing login:

```bash
sudo docker exec tony-pen-test-tracker_api_1 cat /data/secrets/oidc_client_secret; echo
```

It must print your secret. To **rotate**: overwrite the file, then restart the api
container (`sudo docker restart tony-pen-test-tracker_api_1`) so it re-reads at startup.

(For non-Umbrel/dev runs you can instead just set `OIDC_CLIENT_SECRET` directly.)

### 4. Map groups to roles

`OIDC_BOOTSTRAP_*` seeds the two mappings on first boot. Afterwards, an admin manages
them in the app's **Access** tab (or via the admin-only `/idp-role-maps` API): each row
maps a group GUID → `admin`/`member` (+ optional team). A user whose groups map to no
role is denied; the break-glass local admin is always available to fix mappings.

## RBAC summary

- **admin (InfoSec):** full access — tests, findings, risk fields, owner
  reassignment, users/teams, all attachments.
- **member:** sees only findings owned by them or their team; may update
  status/notes and upload attachments on those findings; cannot edit risk
  fields or reassign; cannot create tests/findings.

## Security hardening

Secure-by-default settings for an internet-facing deployment:

| Env var | Default | Effect |
| --- | --- | --- |
| `CORS_ALLOW_ORIGINS` | `""` (none) | Comma-separated browser origins allowed to call the API cross-origin. Empty is correct for the bundled SPA, which is same-origin via the nginx `/api` proxy. Credentials are never allowed (auth is a Bearer header). |
| `API_DOCS_ENABLED` | `false` | When `false`, `/api/docs`, `/api/redoc` and `/api/openapi.json` are disabled so the API surface isn't disclosed. Set `true` in dev to use Swagger UI. |

The frontend nginx config sets `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy` and a restrictive `Content-Security-Policy`. **HSTS** is not set
there — terminate TLS at an external proxy and set `Strict-Transport-Security`
on it.

## Endpoints

- `auth`: `POST /auth/login`
- `teams`: `GET /teams`, `POST /teams` (admin)
- `users`: `GET /users` (admin), `POST /users` (admin)
- `tests`: `GET /tests`, `GET /tests/{id}`, `POST/PATCH/DELETE` (admin)
- `findings`: `GET /findings[?test_id=]`, `GET /findings/{id}`,
  `POST` (admin), `PATCH` (owner/admin, field-gated), `DELETE` (admin)
- attachments:
  - `POST /tests/{id}/attachments` (admin), `GET` list, download via
    `/test-attachments/{id}/download`
  - `POST /findings/{id}/attachments` (owner/admin), `GET` list, download via
    `/finding-attachments/{id}/download`

## Notes

- `sla_status` is computed, not stored: "Out" when a finding is unresolved and
  past `due_date`, else "In".
- File storage is abstracted (`services/storage.py`) — local volume now,
  swappable for Azure Blob in Phase 6.
- Tables are auto-created on startup for Phase 1. Alembic migrations are wired
  in alongside CSV import (Phase 2).

## Next phases

2. CSV import (flexible column mapping per vendor) + Alembic
3. BAU planning view
4. Filterable dashboard
5. ✅ Entra ID / OIDC SSO with group→role mapping
6. Azure Blob storage + deployment manifests
