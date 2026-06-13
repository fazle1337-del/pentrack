# PenTrack — Project Plan

## 1. Data Model

### Organisations / Teams
- `teams` (id, name)
- `users` (id, name, email, auth_type [sso|local], password_hash [nullable], team_id, role [admin|member])

### Tests / Engagements
- `tests`
  - id
  - name
  - tester_reference (vendor name + their reference)
  - scope
  - bau_or_project (enum: BAU | Project)
  - itsm_reference
  - date_logged
  - logged_by_user_id
  - due_date
  - status (Planned | In Progress | Completed)
  - scheduled_date (for BAU planning view)
- `test_attachments` (id, test_id, filename, storage_path, uploaded_by, uploaded_at)

### Findings
- `findings`
  - id
  - test_id (FK)
  - asset_tested
  - user_story
  - vulnerability
  - finding_description
  - test_vendor_initial_recommendation
  - gross_risk_rating (Critical|High|Medium|Low|Info)
  - net_likelihood (Low|Medium|High|Critical)
  - net_impact (Low|Medium|High|Critical)
  - net_rating (Critical|High|Medium|Low|Info)
  - net_risk_rationale
  - remediation_owner_user_id (nullable)
  - remediation_owner_team_id (nullable)
  - status (Open|In Progress|Remediated|Verified|Closed|Transferred|Accepted|Duplicate)
  - due_date
  - sla_status (In|Out — can be computed from due_date + status)
  - additional_information
  - resolver_reference
  - date_logged_in_resolver
  - created_at / updated_at
- `finding_attachments` (id, finding_id, filename, storage_path, uploaded_by, uploaded_at)
- `finding_reassignment_history` (id, finding_id, from_owner, to_owner, changed_by, changed_at)

### CSV Import
- `csv_import_mappings` (id, name, source_column -> target_field JSON, created_by)
- Flexible mapping UI: upload CSV → preview columns → map to finding fields → save mapping (reusable per vendor) → import creates `tests` + `findings`.

---

## 2. RBAC Matrix

| Action | InfoSec (Admin) | Team Member (Consumer) |
|---|---|---|
| View all tests/findings | ✅ | ❌ (only own team's) |
| Create/edit tests | ✅ | ❌ |
| Import CSV | ✅ | ❌ |
| Edit Gross/Net Risk fields | ✅ | ❌ |
| Reassign finding owner | ✅ | ❌ (request only, future) |
| Update finding status/notes (own findings) | ✅ | ✅ |
| Upload attachments to own findings | ✅ | ✅ |
| View dashboard (org-wide) | ✅ | ❌ (own team only) |
| Manage users/teams | ✅ | ❌ |
| BAU Planning — create/edit | ✅ | ❌ |
| BAU Planning — view | ✅ | ✅ (read-only) |

Auth: Microsoft Entra ID (OIDC) primary; local email/password accounts as fallback (flag on user record).

---

## 3. Tech Stack

- **Backend**: FastAPI (Python), SQLAlchemy, Alembic migrations
- **DB**: PostgreSQL
- **Frontend**: React + Vite, Tailwind
- **Auth**: `msal` / Authlib for Entra ID OIDC + local JWT auth fallback
- **File storage**: local volume (`/data/attachments`), abstracted behind a storage interface so it can swap to Azure Blob later
- **Containerization**: docker-compose (api, frontend, postgres) — runs on Pi5 (arm64-compatible images), portable to Azure Container Apps/AKS

---

## 4. Phased Build Plan

**Phase 1 — Core MVP**
- DB schema + migrations
- Auth (local accounts first, Entra ID stubbed)
- Teams/Users CRUD (admin only)
- Tests CRUD
- Findings CRUD with full field set, RBAC enforced
- Attachments upload/download (tests + findings)

**Phase 2 — CSV Import**
- Upload CSV, column-mapping UI, save mapping per vendor
- Bulk create tests + findings from import
- Validation/error reporting on import

**Phase 3 — BAU Planning View**
- Calendar/list view of scheduled tests
- Status + scheduled date + attachments
- Filter by team/status/date range

**Phase 4 — Dashboard**
- Filterable views: by severity, status, team, owner, SLA in/out, date range
- Counts/charts (findings by severity, open vs closed, overdue)

**Phase 5 — Entra ID SSO**
- OIDC integration, account linking, role mapping

**Phase 6 — Azure portability**
- Externalize storage to Azure Blob, confirm Postgres → Azure DB for Postgres compatibility, deployment manifests

---

## 5. Open Items / Future Enhancements
- Email notifications on reassignment / SLA breach
- Likelihood × Impact → suggested Net Rating matrix (UI hint)
- CSV export of filtered views
