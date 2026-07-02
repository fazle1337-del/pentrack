"""Admin CRUD for the EasyVista bearer token (2026-07-01 correction): write-only
PUT, boolean-only GET — mirrors test_teams_admin.py's TestClient fixture.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.enums import AuthType, Role
from app.models.models import User

ADMIN_EMAIL = "admin@example.com"
ADMIN_PW = "correct-horse"


@pytest.fixture(autouse=True)
def no_env_fallback_token():
    """Isolate from other test modules' leftover get_settings() state (it's
    lru_cached and shared process-wide) so "unset" here means actually unset,
    regardless of test run order."""
    s = get_settings()
    saved = s.easyvista_bearer_token
    s.easyvista_bearer_token = ""
    yield
    s.easyvista_bearer_token = saved


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    tc = TestClient(app)
    # Distinct fake IP so this file's logins don't share the login-rate-limit
    # counter with other test files/fixtures (see test_login_ratelimit.py).
    res = tc.post(
        "/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PW},
        headers={"X-Forwarded-For": "203.0.113.32"},
    )
    token = res.json()["access_token"]
    tc.headers.update({"Authorization": f"Bearer {token}"})
    yield tc
    app.dependency_overrides.clear()


def test_starts_unset(client):
    body = client.get("/easyvista-config").json()
    assert body["bearer_token_set"] is False
    assert body["poll_enabled"] is False  # settings.easyvista_poll_enabled default


def test_put_sets_token_but_never_returns_it(client):
    res = client.put("/easyvista-config", json={"bearer_token": "s3cret-token"})
    assert res.status_code == 200
    assert res.json()["bearer_token_set"] is True
    assert "s3cret-token" not in res.text


def test_put_with_blank_token_leaves_existing_value_unchanged(client):
    client.put("/easyvista-config", json={"bearer_token": "s3cret-token"})
    res = client.put("/easyvista-config", json={"bearer_token": ""})
    assert res.json()["bearer_token_set"] is True


def test_requires_admin(client):
    client.headers.pop("Authorization")
    res = client.get("/easyvista-config")
    assert res.status_code in (401, 403)


def test_set_and_read_back_poll_settings(client):
    res = client.put(
        "/easyvista-config",
        json={
            "poll_enabled": True,
            "poll_open_interval_seconds": 1800,
            "poll_closed_interval_seconds": 43200,
            "poll_closed_lookback_days": 90,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["poll_enabled"] is True
    assert body["poll_open_interval_seconds"] == 1800
    assert body["poll_closed_interval_seconds"] == 43200
    assert body["poll_closed_lookback_days"] == 90


def test_omitted_poll_fields_leave_existing_values_unchanged(client):
    client.put("/easyvista-config", json={"poll_enabled": True, "poll_open_interval_seconds": 1800})
    # A later PUT that only touches the token must not reset poll settings.
    res = client.put("/easyvista-config", json={"bearer_token": "another-token"})
    body = res.json()
    assert body["poll_enabled"] is True
    assert body["poll_open_interval_seconds"] == 1800
