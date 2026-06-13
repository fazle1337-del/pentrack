from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import AuthType, Role
from app.models.models import User
from app.routers import attachments, auth, findings, teams_users, tests

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1: create tables directly. Alembic migrations wired in Phase 2.
    Base.metadata.create_all(bind=engine)
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


@app.get("/health")
def health():
    return {"status": "ok"}
