"""EasyVista push-gating (2026-07-01): assignment is group-based, so pushing
requires a team-owned finding whose team has an EV group mapped. Mirrors
test_teams_admin.py's TestClient fixture. The actual EV HTTP call is
monkeypatched — the request/response shape itself is covered by
test_easyvista.py at the service level.
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
from app.models.enums import AuthType, FindingStatus, Role
from app.models.models import Finding, Team, User
from app.models.models import Test as Engagement
from app.services import easyvista

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
    s = get_settings()
    saved_enabled = s.easyvista_enabled
    s.easyvista_enabled = True

    client = TestClient(app)
    # Distinct fake IP so this file's logins don't share the login-rate-limit
    # counter with other test files/fixtures (see test_login_ratelimit.py).
    res = client.post(
        "/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PW},
        headers={"X-Forwarded-For": "203.0.113.33"},
    )
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client, Session
    app.dependency_overrides.clear()
    s.easyvista_enabled = saved_enabled


def _make_finding(Session, *, team_id: int | None) -> int:
    db = Session()
    test = Engagement(name="Engagement 1")
    db.add(test)
    db.flush()
    finding = Finding(
        test_id=test.id,
        vulnerability="SQLi",
        status=FindingStatus.open,
        remediation_owner_team_id=team_id,
    )
    db.add(finding)
    db.commit()
    fid = finding.id
    db.close()
    return fid


def test_push_blocked_without_owning_team(ctx):
    client, Session = ctx
    fid = _make_finding(Session, team_id=None)
    res = client.post(f"/itsm/findings/{fid}/push")
    assert res.status_code == 409
    assert "no owning team" in res.json()["detail"]


def test_push_blocked_when_team_has_no_ev_group(ctx):
    client, Session = ctx
    tid = client.post("/teams", json={"name": "Web Team"}).json()["id"]
    fid = _make_finding(Session, team_id=tid)
    res = client.post(f"/itsm/findings/{fid}/push")
    assert res.status_code == 409
    assert "no EasyVista group mapped" in res.json()["detail"]


def test_push_succeeds_and_passes_ev_group_id(ctx, monkeypatch):
    client, Session = ctx
    tid = client.post("/teams", json={"name": "Web Team"}).json()["id"]
    client.patch(f"/teams/{tid}", json={"name": "Web Team", "ev_group_id": "GRP-1"})
    fid = _make_finding(Session, team_id=tid)

    captured = {}

    def fake_push_finding(db, finding, *, client=None, ev_group_id=None):
        captured["ev_group_id"] = ev_group_id
        return {"reference": "RFC0000001", "href": "https://x/requests/1"}

    monkeypatch.setattr(easyvista, "push_finding", fake_push_finding)

    res = client.post(f"/itsm/findings/{fid}/push")
    assert res.status_code == 200, res.text
    assert res.json() == {"itsm_reference": "RFC0000001", "href": "https://x/requests/1"}
    assert captured["ev_group_id"] == "GRP-1"


def test_push_404s_when_flag_off(ctx):
    client, Session = ctx
    get_settings().easyvista_enabled = False
    fid = _make_finding(Session, team_id=None)
    res = client.post(f"/itsm/findings/{fid}/push")
    assert res.status_code == 404


def test_list_ev_groups(ctx, monkeypatch):
    client, _ = ctx
    monkeypatch.setattr(
        easyvista, "list_groups", lambda *a, **kw: [{"GROUP_ID": "1", "GROUP_EN": "Web Team"}]
    )
    res = client.get("/itsm/groups")
    assert res.status_code == 200
    assert res.json() == [{"GROUP_ID": "1", "GROUP_EN": "Web Team"}]


def test_list_ev_groups_404s_when_flag_off(ctx):
    client, _ = ctx
    get_settings().easyvista_enabled = False
    res = client.get("/itsm/groups")
    assert res.status_code == 404


def test_refresh_blocked_when_never_pushed(ctx):
    client, Session = ctx
    fid = _make_finding(Session, team_id=None)  # itsm_reference is None
    res = client.post(f"/itsm/findings/{fid}/refresh")
    assert res.status_code == 409
    assert "hasn't been pushed" in res.json()["detail"]


def test_refresh_updates_cached_status(ctx, monkeypatch):
    client, Session = ctx
    fid = _make_finding(Session, team_id=None)
    db = Session()
    finding = db.get(Finding, fid)
    finding.itsm_reference = "RFC0001234"
    db.commit()
    db.close()

    monkeypatch.setattr(
        easyvista,
        "get_request_status",
        lambda rfc, db, **kw: {"status_label": "Closed", "status_guid": "g1", "closed": True},
    )

    res = client.post(f"/itsm/findings/{fid}/refresh")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["itsm_status_label"] == "Closed"
    assert body["itsm_closed"] is True
    assert body["itsm_synced_at"] is not None

    # Persisted, not just returned.
    db = Session()
    refreshed = db.get(Finding, fid)
    assert refreshed.itsm_status_label == "Closed"
    assert refreshed.itsm_closed is True
    db.close()


def test_refresh_404s_when_finding_missing(ctx):
    client, _ = ctx
    res = client.post("/itsm/findings/999999/refresh")
    assert res.status_code == 404


def test_refresh_404s_when_flag_off(ctx):
    client, Session = ctx
    get_settings().easyvista_enabled = False
    fid = _make_finding(Session, team_id=None)
    res = client.post(f"/itsm/findings/{fid}/refresh")
    assert res.status_code == 404
