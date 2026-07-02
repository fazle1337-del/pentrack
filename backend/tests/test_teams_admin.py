"""Teams admin CRUD (issue #13): create / rename / delete with reference guard.

Admin-guarded routes are driven through TestClient with an in-memory SQLite DB.
A seeded admin logs in to get a bearer token.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.enums import AuthType, FindingStatus, Role
from app.models.models import Finding, Team, User
from app.models.models import Test as Engagement  # avoid pytest collecting "Test"

ADMIN_EMAIL = "admin@example.com"
ADMIN_PW = "correct-horse"


@pytest.fixture
def ctx():
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
    client = TestClient(app)
    # Distinct fake IP so this file's logins don't share the login-rate-limit
    # counter with other test files/fixtures (see test_login_ratelimit.py).
    res = client.post(
        "/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PW},
        headers={"X-Forwarded-For": "203.0.113.31"},
    )
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client, Session
    app.dependency_overrides.clear()


def test_create_rename_delete(ctx):
    client, _ = ctx
    created = client.post("/teams", json={"name": "Payments"})
    assert created.status_code == 201, created.text
    tid = created.json()["id"]

    renamed = client.patch(f"/teams/{tid}", json={"name": "Payments Eng"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Payments Eng"

    assert client.delete(f"/teams/{tid}").status_code == 204
    assert all(t["id"] != tid for t in client.get("/teams").json())


def test_rename_duplicate_conflicts(ctx):
    client, _ = ctx
    client.post("/teams", json={"name": "A"})
    b = client.post("/teams", json={"name": "B"}).json()
    assert client.patch(f"/teams/{b['id']}", json={"name": "A"}).status_code == 409


def test_set_and_clear_ev_group_id(ctx):
    client, _ = ctx
    tid = client.post("/teams", json={"name": "Web Team"}).json()["id"]

    res = client.patch(f"/teams/{tid}", json={"name": "Web Team", "ev_group_id": "GRP-1"})
    assert res.status_code == 200
    assert res.json()["ev_group_id"] == "GRP-1"

    # Omitting the field on a plain rename must NOT wipe it.
    res = client.patch(f"/teams/{tid}", json={"name": "Web Team 2"})
    assert res.status_code == 200
    assert res.json()["ev_group_id"] == "GRP-1"

    # Explicit "" clears it.
    res = client.patch(f"/teams/{tid}", json={"name": "Web Team 2", "ev_group_id": ""})
    assert res.status_code == 200
    assert res.json()["ev_group_id"] is None


def test_ev_group_id_uniqueness_conflict(ctx):
    client, _ = ctx
    a = client.post("/teams", json={"name": "A"}).json()["id"]
    b = client.post("/teams", json={"name": "B"}).json()["id"]
    client.patch(f"/teams/{a}", json={"name": "A", "ev_group_id": "GRP-1"})

    res = client.patch(f"/teams/{b}", json={"name": "B", "ev_group_id": "GRP-1"})
    assert res.status_code == 409
    assert "GRP-1" in res.json()["detail"]


def test_delete_blocked_when_referenced(ctx):
    client, Session = ctx
    tid = client.post("/teams", json={"name": "Owned"}).json()["id"]

    # Attach a finding to the team so deletion is blocked.
    db = Session()
    test = Engagement(name="Engagement 1")
    db.add(test)
    db.flush()
    db.add(
        Finding(
            test_id=test.id,
            vulnerability="X",
            status=FindingStatus.open,
            remediation_owner_team_id=tid,
        )
    )
    db.commit()
    db.close()

    res = client.delete(f"/teams/{tid}")
    assert res.status_code == 409
    assert "finding" in res.json()["detail"]
    # Still present.
    assert any(t["id"] == tid for t in client.get("/teams").json())
