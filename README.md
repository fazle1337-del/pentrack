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
- Local accounts now; Microsoft Entra ID SSO arrives in Phase 5.

## RBAC summary

- **admin (InfoSec):** full access — tests, findings, risk fields, owner
  reassignment, users/teams, all attachments.
- **member:** sees only findings owned by them or their team; may update
  status/notes and upload attachments on those findings; cannot edit risk
  fields or reassign; cannot create tests/findings.

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
5. Entra ID SSO
6. Azure Blob storage + deployment manifests
