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
    res = client.post(
        "/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PW}
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
