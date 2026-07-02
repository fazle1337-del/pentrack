import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import AuthType, Role
from app.models.models import User
from app.routers import (
    attachments,
    auth,
    bookings,
    easyvista_config,
    findings,
    idp_maps,
    imports,
    itsm,
    oidc_config,
    related,
    scopes,
    teams_users,
    tests,
)
from app.services.easyvista_poller import poll_once

settings = get_settings()
_logger = logging.getLogger(__name__)


def seed_admin():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin = User(
                name=settings.seed_admin_name,
                email=settings.seed_admin_email,
                auth_type=AuthType.local,
                role=Role.admin,
                password_hash=hash_password(settings.seed_admin_password),
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


from sqlalchemy import inspect, text


def sync_missing_columns():
    """Lightweight, non-destructive schema sync: for each mapped table, ADD any
    columns present in the model but missing from the live DB. Covers simple
    additive changes (like adding itsm_reference to findings) without a full
    Alembic setup. Type/constraint changes still need a real migration."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all handles brand-new tables
            live_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in live_cols:
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}')
                )


def sync_easyvista_unique_indexes():
    """`sync_missing_columns`'s ADD COLUMN doesn't carry over UNIQUE (only the
    type is compiled, not constraints) — so the EasyVista id columns added
    2026-07-01 (Team.ev_group_id, User.staff_number, User.ev_employee_id) need
    an explicit follow-up on existing databases. New deployments already get
    the constraint via create_all; this is idempotent so it's a no-op there.
    A unique index on a nullable column allows any number of NULLs (each NULL
    is distinct), which is exactly what's wanted while most rows are unmapped.
    """
    with engine.begin() as conn:
        if "teams" not in set(inspect(conn).get_table_names()):
            return
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_teams_ev_group_id "
                "ON teams (ev_group_id)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_staff_number "
                "ON users (staff_number)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_ev_employee_id "
                "ON users (ev_employee_id)"
            )
        )


def migrate_schedule_feature():
    """One-time, idempotent migration for the BAU schedule feature. The app is
    pre-production so test data is not preserved:
      - swap tests.status from the old `teststatus` enum to `engagementstatus`
        (the new type is created by create_all via the bookings table),
      - drop the retired free-text tests.scope column,
      - index tests.unique_test_reference (the shared link key).
    """
    from app.models.models import Test

    status_type = Test.__table__.c.status.type
    type_name = (status_type.name or "engagementstatus").lower()
    default_label = list(status_type.enums)[0]
    col_ddl = status_type.compile(dialect=engine.dialect)

    with engine.begin() as conn:
        if "tests" not in set(inspect(conn).get_table_names()):
            return
        udt = conn.execute(
            text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name='tests' AND column_name='status'"
            )
        ).scalar()
        if udt is None or udt.lower() != type_name:
            conn.execute(text("ALTER TABLE tests DROP COLUMN IF EXISTS status"))
            conn.execute(
                text(
                    f"ALTER TABLE tests ADD COLUMN status {col_ddl} "
                    f"NOT NULL DEFAULT '{default_label}'"
                )
            )
            conn.execute(text("DROP TYPE IF EXISTS teststatus"))
        conn.execute(text("ALTER TABLE tests DROP COLUMN IF EXISTS scope"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tests_unique_test_reference "
                "ON tests (unique_test_reference)"
            )
        )


def seed_idp_bootstrap():
    """Non-prod convenience: if SSO is on and bootstrap groups are configured,
    seed the corresponding IdpRoleMap rows once (only when the table is empty),
    so a fresh Keycloak realm logs in without manual mapping setup."""
    if not settings.oidc_enabled:
        return
    if not (settings.oidc_bootstrap_admin_group or settings.oidc_bootstrap_member_group):
        return
    from app.models.models import IdpRoleMap

    db = SessionLocal()
    try:
        if db.query(IdpRoleMap).count() > 0:
            return
        rows = []
        if settings.oidc_bootstrap_admin_group:
            rows.append(
                IdpRoleMap(
                    idp_group_id=settings.oidc_bootstrap_admin_group,
                    label="bootstrap admin group",
                    role=Role.admin,
                )
            )
        if settings.oidc_bootstrap_member_group:
            rows.append(
                IdpRoleMap(
                    idp_group_id=settings.oidc_bootstrap_member_group,
                    label="bootstrap member group",
                    role=Role.member,
                )
            )
        db.add_all(rows)
        db.commit()
    finally:
        db.close()


async def _easyvista_poller_loop():
    """Ticks every `easyvista_poll_tick_seconds`; poll_once() itself no-ops
    unless polling is enabled (DB-over-env), so this stays cheap when off.
    Runs poll_once (sync DB/HTTP work) in a thread so it never blocks the
    event loop that's also serving API requests."""
    while True:
        if settings.easyvista_enabled:
            db = SessionLocal()
            try:
                await asyncio.to_thread(poll_once, db)
            except Exception:
                _logger.exception("EasyVista poll tick failed")
            finally:
                db.close()
        await asyncio.sleep(settings.easyvista_poll_tick_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_schedule_feature()
    sync_missing_columns()
    sync_easyvista_unique_indexes()
    seed_admin()
    seed_idp_bootstrap()
    poller_task = asyncio.create_task(_easyvista_poller_loop())
    try:
        yield
    finally:
        poller_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poller_task


# Disable interactive docs unless explicitly enabled (issue #9): an internet-
# facing instance shouldn't disclose its full API surface to anonymous callers.
_docs_kwargs = (
    {}
    if settings.api_docs_enabled
    else {"docs_url": None, "redoc_url": None, "openapi_url": None}
)
app = FastAPI(
    title="PenTrack API", version="0.1.0", lifespan=lifespan, **_docs_kwargs
)

# Login rate limiting (issue #6). The limiter instance is shared with the
# decorated route; register it on the app + install the 429 handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS (issue #7): restrict to the configured origin(s) instead of "*", and
# never allow credentials (the app authenticates with a Bearer header, not
# cookies). Empty list = no cross-origin access — fine, since the SPA is
# same-origin via the nginx /api proxy.
_cors_origins = [
    o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(idp_maps.router)
app.include_router(oidc_config.router)
app.include_router(teams_users.router)
app.include_router(tests.router)
app.include_router(findings.router)
app.include_router(attachments.router)
app.include_router(imports.router)
app.include_router(bookings.router)
app.include_router(scopes.router)
app.include_router(related.router)
app.include_router(itsm.router)
app.include_router(easyvista_config.router)


@app.get("/health")
def health():
    return {"status": "ok"}
