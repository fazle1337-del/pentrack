"""Token invalidation / server-side logout (issue #5).

Drives the real FastAPI app through TestClient with an in-memory SQLite DB
injected via the get_db dependency override. The app's lifespan (which would hit
the real engine) is intentionally NOT run — TestClient is used without its
context manager, so create_all/seed run here instead.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.enums import AuthType, Role
from app.models.models import User

ADMIN_EMAIL = "admin@example.com"
ADMIN_PW = "correct-horse"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory DB across threads
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    seed = Session()
    seed.add(
        User(
            name="Admin",
            email=ADMIN_EMAIL,
            auth_type=AuthType.local,
            role=Role.admin,
            password_hash=hash_password(ADMIN_PW),
        )
    )
    seed.commit()
    seed.close()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client):
    res = client.post(
        "/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PW}
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_token_works_then_logout_invalidates_it(client):
    token = _login(client)
    auth = {"Authorization": f"Bearer {token}"}

    # Token is valid before logout.
    assert client.get("/auth/me", headers=auth).status_code == 200

    # Logout bumps token_version server-side.
    assert client.post("/auth/logout", headers=auth).status_code == 204

    # The same token is now rejected — not merely dropped client-side.
    assert client.get("/auth/me", headers=auth).status_code == 401


def test_logout_does_not_affect_a_freshly_issued_token(client):
    old = _login(client)
    client.post("/auth/logout", headers={"Authorization": f"Bearer {old}"})

    # A login after logout mints a token at the new token_version, so it works.
    new = _login(client)
    assert new != old
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {new}"})
    assert res.status_code == 200
