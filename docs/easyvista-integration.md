# EasyVista (ITSM) integration

Pushes a finding into **EasyVista Service Manager** as a request/incident and
stores the returned reference on the finding's `itsm_reference`. **Optional and
OFF by default** (`easyvista_enabled`) — it ships dark and is validated against a
real tenant later, mirroring the SSO rollout.

It was built **without a live EasyVista tenant**: the code targets the documented
[create-a-request](https://docs.easyvista.com/docs/rest-api-create-an-incident-request)
REST contract, and is exercised with a mock and a local stub (below). Two things
must be confirmed against a real tenant before relying on it — see
[Open questions](#open-questions-confirm-against-a-real-tenant).

## How it works

```
POST {host}/api/v1/{account}/requests   (HTTP Basic auth)
  -> 201 {"HREF": ".../requests/{id}"}   # trailing id is stored as itsm_reference
```

1. The frontend can show a **Push to EasyVista** action when `GET /itsm/config`
   reports `itsm_enabled: true`.
2. An admin calls `POST /itsm/findings/{id}/push` (admin-only; 404s when the flag
   is off). Pushing is an **explicit per-finding action**, never automatic on
   finding create — so nothing leaves the app until an operator opts in.
3. The backend maps the finding to a request body, POSTs it with Basic auth,
   parses the `HREF`, and saves the trailing request id to `finding.itsm_reference`.
4. Errors are mapped: `401` → bad credentials, `406` → unknown requestor/recipient
   domain, anything else → `502` to the caller.

The whole EasyVista surface lives in **one module**, `app/services/easyvista.py`
— that isolation *is* the adapter boundary. Retarget a different ITSM by swapping
that file; no abstract base class until a second backend exists.

| Concern | Location |
|---|---|
| Mapping + REST client + persist | `backend/app/services/easyvista.py` |
| Routes (`/itsm/config`, push) | `backend/app/routers/itsm.py` |
| Settings | `backend/app/core/config.py` |
| Mock tests (no tenant) | `backend/tests/test_easyvista.py` |
| Local stub server | `backend/tests/easyvista_stub.py` |

## Configuration

There is **no in-app UI for the connection** — it is deployment-level env, like
the OIDC config. (The IdP role maps live in the DB and are editable in the Access
tab; connection secrets do not.) Each setting is read from its uppercased name:

| Setting | Env var | Secret? | Goes where |
|---|---|---|---|
| Enable the integration | `EASYVISTA_ENABLED=true` | no | compose |
| Host | `EASYVISTA_HOST=https://<account>.easyvista.com` | no | compose |
| Account / path segment | `EASYVISTA_ACCOUNT` | no | compose |
| Integration login | `EASYVISTA_LOGIN` | no | compose |
| **Password** | `EASYVISTA_PASSWORD_FILE=/data/secrets/easyvista_password` | **yes** | **file on the Pi** |
| Catalog GUID (request subject) | `EASYVISTA_CATALOG_GUID` | no | compose |
| Requestor/recipient mailbox | `EASYVISTA_REQUESTOR_MAIL` | no | compose |
| HTTP timeout (default 30s) | `EASYVISTA_TIMEOUT_SECONDS` | no | compose |

The password uses the file pattern (`easyvista_password_file` wins over the env
var when the file exists) — the **same approach as `OIDC_CLIENT_SECRET_FILE`**,
because the repos mirror to public GitHub and **secrets must never be in the
compose**.

> One of `EASYVISTA_CATALOG_GUID` / `EASYVISTA_CATALOG_CODE` is **required** by
> the API (GUID preferred). Its value comes from the tenant's EV catalogue.

## Deploying when creds arrive

1. **Build + push** new images under a fresh semver tag (never overwrite a
   published tag — see the root `CLAUDE.md` deploy section).
2. **Edit the `Tony-Umbrel` compose** (`api`/backend service): add the non-secret
   `EASYVISTA_*` env vars above; bump the version in both store files.
3. **Drop the password file on the Pi.** The OIDC secret already bind-mounts
   `${APP_DATA_DIR}/data/secrets` → `/data/secrets`, so reuse that mount and just
   add the file (contains only the password):
   ```
   ${APP_DATA_DIR}/data/secrets/easyvista_password
   ```
   If you instead point `EASYVISTA_PASSWORD_FILE` at a path that is **not** already
   mounted, you hit the bind-mount ordering gotcha (the file must exist *before*
   the container is created, then the container recreated) — reusing the existing
   `/data/secrets` mount avoids it.
4. **Recreate the container** (Stop+Start or `--force-recreate`). A plain
   *restart* does **not** re-read env vars. This also pulls the new image tag.
5. **Verify:**
   ```bash
   sudo docker exec tony-pen-test-tracker_api_1 cat /data/secrets/easyvista_password
   curl -s http://127.0.0.1:8099/api/itsm/config        # {"itsm_enabled": true}
   ```
   then push one real finding to confirm auth + the `catalog_guid`.

## Testing without a tenant

### Mock tests (zero setup — fake EasyVista is in-memory)

`pytest` drives the service through an `httpx.MockTransport` that returns the
documented `201`/`401`/`406` responses. No server, no network, no creds.

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

### Local stub (fake EasyVista runs on your laptop)

`tests/easyvista_stub.py` is a tiny server that *pretends to be EasyVista* on
`127.0.0.1:9001`. Point the backend's `EASYVISTA_HOST` at it (not at
easyvista.com) and the full push path runs end-to-end against your own stub.

```bash
# terminal 1 — run the stub
cd backend && uvicorn tests.easyvista_stub:app --port 9001

# terminal 2 — configure the backend to use the stub, then start the app
export EASYVISTA_ENABLED=true
export EASYVISTA_HOST=http://127.0.0.1:9001
export EASYVISTA_ACCOUNT=50012
export EASYVISTA_CATALOG_GUID=GUID-LOCAL
export EASYVISTA_REQUESTOR_MAIL=pentrack@local.test
export EASYVISTA_LOGIN=api EASYVISTA_PASSWORD=stub   # plain env var ok locally; file pattern is prod-only
# ... start the app, then POST /itsm/findings/{id}/push as an admin
```

Set `STUB_STATUS=401` (or `406`) in the stub's env to exercise the failure paths.

## Open questions (confirm against a real tenant)

Both are commented in `app/services/easyvista.py`:

1. **Auth mechanism.** HTTP Basic is assumed — the linked create-request doc only
   describes the `401` *failure*, not the mechanism. Confirm Basic against a live
   instance.
2. **Catalogue + risk mapping.** The tenant-specific `catalog_guid`, and any
   risk-rating → EV urgency/severity ID mapping, are deliberately left out rather
   than guessed. Wire them once a real catalogue is known.
