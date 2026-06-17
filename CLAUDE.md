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
4. BAU planning module
5. Dashboard
6. Entra SSO
7. Azure portability

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

**2. Release (Pi).** Bump both image tags to `X.Y.Z` in the Umbrel app compose, then pull + recreate (a `:latest`-style restart won't re-pull; changing the tag forces it):

```bash
sudo docker compose -f ~/umbrel/app-data/tony-pen-test-tracker/docker-compose.yml pull
sudo docker compose -f ~/umbrel/app-data/tony-pen-test-tracker/docker-compose.yml up -d --force-recreate
```

Hard-refresh the browser afterwards — the frontend is nginx static + a service worker, so old assets cache.

**3. Verify.** A dashboard restart does **not** pull. Before calling it deployed, confirm the live container runs the new tag and its digest matches what you pushed:

```bash
sudo docker inspect tony-pen-test-tracker_api_1 --format '{{.Config.Image}}'    # expect :X.Y.Z
docker buildx imagetools inspect tonybooom/pen-test-tracker-frontend:X.Y.Z | grep -i digest
```

## Umbrel-specific constraints

- Umbrel community apps don't handle `.env`-style secrets reliably. Use `${APP_SEED}` for the JWT secret and Postgres password, `${APP_PASSWORD}` for the seed admin password. Hardcode other env vars directly in the compose file.
- **App-store repo is strictly separate from the main project repo.** The `tony-pen-test-tracker/` folder must contain **only** `docker-compose.yml` and `umbrel-app.yml`. Watch for main-project files leaking into it — this has bitten us repeatedly.

## Database migrations

Additive schema changes must be **idempotent** to avoid data loss on existing deployments. The startup migration `sync_missing_columns` handles additive column changes on existing databases without data loss. Follow that pattern for new additive changes.

## Getting the initial admin login

- Username: `admin@example.com`
- Password: `sudo docker exec tony-pen-test-tracker_api_1 printenv SEED_ADMIN_PASSWORD`

## Working conventions

- State assumptions before writing code. Ask when ambiguous.
- Prefer minimal, simple solutions. No unnecessary abstractions.
- Make surgical changes only — touch nothing outside the task scope.
- End every task by verifying it meets the stated success criteria (for deploy tasks, that means the `CACHE_NAME` check above).

## Known fixed bugs (for context)

`itsm_reference` field silently dropped on save; missing attachment deletion endpoint/UI; vendor recommendation was display-only and hidden when empty; Additional Information and Date Logged in Resolver missing from the finding drawer. All resolved.
