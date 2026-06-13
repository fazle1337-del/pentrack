from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import AuthType, Role
from app.models.models import User
from app.routers import attachments, auth, findings, imports, teams_users, tests

settings = get_settings()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    sync_missing_columns()
    seed_admin()
    yield


app = FastAPI(title="PenTrack API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(teams_users.router)
app.include_router(tests.router)
app.include_router(findings.router)
app.include_router(attachments.router)
app.include_router(imports.router)


@app.get("/health")
def health():
    return {"status": "ok"}
