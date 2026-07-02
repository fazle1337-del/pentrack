"""EasyVista push-gating (2026-07-01): assignment is group-based, so pushing
requires a team-owned finding whose team has an EV group mapped. Mirrors
test_teams_admin.py's TestClient fixture. The actual EV HTTP call is
monkeypatched — the request/response shape itself is covered by
test_easyvista.py at the service level.
"""

import itertools

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.enums import AuthType, FindingStatus, Role
from app.models.models import Finding, FindingItsmComment, Team, User
from app.models.models import Test as Engagement
from app.services import easyvista

ADMIN_EMAIL = "admin@example.com"
ADMIN_PW = "correct-horse"

# Each test in this file logs in once via the `ctx` fixture; the login
# rate-limiter is in-process and keyed on IP, so a shared fixed IP caps this
# file at 10 tests (issue hit when Phase B added more). A unique IP per
# fixture instantiation sidesteps that instead of sharing one counter.
_login_ips = (f"203.0.113.{n}" for n in itertools.count(40))


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
    # Distinct fake IP per test so this file's logins don't collide with each
    # other or with other test files' fixtures (see test_login_ratelimit.py).
    res = client.post(
        "/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PW},
        headers={"X-Forwarded-For": next(_login_ips)},
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


def _member_headers(Session, *, team_id: int | None, email="member@example.com") -> dict:
    db = Session()
    user = User(
        name="Member",
        email=email,
        auth_type=AuthType.local,
        role=Role.member,
        password_hash=hash_password("x"),
        team_id=team_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), user.token_version or 0)
    db.close()
    return {"Authorization": f"Bearer {token}"}


_FAKE_COMMENTS = [
    {
        "ev_action_id": "1",
        "author": "pentrack",
        "body": "Original description.",
        "action_type": "Description",
        "posted_at": None,
        "closed": None,
    },
    {
        "ev_action_id": "2",
        "author": "EV Tech",
        "body": "Working on it.",
        "action_type": "Note",
        "posted_at": None,
        "closed": None,
    },
]


def _pushed_finding(Session, *, team_id: int | None) -> int:
    fid = _make_finding(Session, team_id=team_id)
    db = Session()
    finding = db.get(Finding, fid)
    finding.itsm_reference = "RFC0001234"
    db.commit()
    db.close()
    return fid


def test_comments_sync_404s_when_flag_off(ctx):
    client, Session = ctx
    get_settings().easyvista_enabled = False
    fid = _pushed_finding(Session, team_id=None)
    res = client.post(f"/itsm/findings/{fid}/comments/sync")
    assert res.status_code == 404


def test_comments_sync_blocked_when_never_pushed(ctx):
    client, Session = ctx
    fid = _make_finding(Session, team_id=None)  # itsm_reference is None
    res = client.post(f"/itsm/findings/{fid}/comments/sync")
    assert res.status_code == 409
    assert "hasn't been pushed" in res.json()["detail"]


def test_comments_sync_and_get_as_admin(ctx, monkeypatch):
    client, Session = ctx
    fid = _pushed_finding(Session, team_id=None)
    monkeypatch.setattr(
        easyvista, "get_request_comments", lambda rfc, db, **kw: _FAKE_COMMENTS
    )

    res = client.post(f"/itsm/findings/{fid}/comments/sync")
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body) == 2
    assert {c["author"] for c in body} == {"pentrack", "EV Tech"}

    res = client.get(f"/itsm/findings/{fid}/comments")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_comments_sync_replaces_rather_than_duplicates(ctx, monkeypatch):
    client, Session = ctx
    fid = _pushed_finding(Session, team_id=None)
    monkeypatch.setattr(
        easyvista, "get_request_comments", lambda rfc, db, **kw: _FAKE_COMMENTS
    )

    client.post(f"/itsm/findings/{fid}/comments/sync")
    client.post(f"/itsm/findings/{fid}/comments/sync")

    db = Session()
    count = db.query(FindingItsmComment).filter(FindingItsmComment.finding_id == fid).count()
    db.close()
    assert count == 2


def test_comments_403_for_non_owning_member(ctx, monkeypatch):
    client, Session = ctx
    tid = client.post("/teams", json={"name": "Web Team"}).json()["id"]
    fid = _pushed_finding(Session, team_id=tid)
    monkeypatch.setattr(
        easyvista, "get_request_comments", lambda rfc, db, **kw: _FAKE_COMMENTS
    )

    headers = _member_headers(Session, team_id=None)  # no team, doesn't own this finding
    res = client.get(f"/itsm/findings/{fid}/comments", headers=headers)
    assert res.status_code == 403
    res = client.post(f"/itsm/findings/{fid}/comments/sync", headers=headers)
    assert res.status_code == 403


def test_comments_visible_to_owning_team_member(ctx, monkeypatch):
    client, Session = ctx
    tid = client.post("/teams", json={"name": "Web Team"}).json()["id"]
    fid = _pushed_finding(Session, team_id=tid)
    monkeypatch.setattr(
        easyvista, "get_request_comments", lambda rfc, db, **kw: _FAKE_COMMENTS
    )

    headers = _member_headers(Session, team_id=tid)
    res = client.post(f"/itsm/findings/{fid}/comments/sync", headers=headers)
    assert res.status_code == 200, res.text
    res = client.get(f"/itsm/findings/{fid}/comments", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2
