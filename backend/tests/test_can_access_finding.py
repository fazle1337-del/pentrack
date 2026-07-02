"""Unit tests for the shared finding-visibility rule (core/deps.can_access_finding),
lifted out of routers/findings.py so routers/itsm.py's comment routes (Phase B)
could reuse it without duplicating the security check. Pure function — no DB
needed, just in-memory model instances."""

from app.core.deps import can_access_finding
from app.models.enums import Role
from app.models.models import Finding, User


def _user(role=Role.member, id=1, team_id=None) -> User:
    return User(id=id, name="U", email="u@example.com", role=role, team_id=team_id)


def _finding(owner_user_id=None, owner_team_id=None) -> Finding:
    return Finding(
        id=1,
        test_id=1,
        remediation_owner_user_id=owner_user_id,
        remediation_owner_team_id=owner_team_id,
    )


def test_admin_can_access_any_finding():
    assert can_access_finding(_user(role=Role.admin, id=99), _finding()) is True


def test_owner_user_can_access():
    assert can_access_finding(_user(id=5), _finding(owner_user_id=5)) is True


def test_owning_team_member_can_access():
    assert can_access_finding(_user(id=5, team_id=7), _finding(owner_team_id=7)) is True


def test_unrelated_member_is_denied():
    assert can_access_finding(_user(id=5, team_id=7), _finding(owner_team_id=8)) is False
    assert can_access_finding(_user(id=5), _finding(owner_user_id=6)) is False


def test_unowned_finding_is_denied_for_member():
    assert can_access_finding(_user(id=5, team_id=7), _finding()) is False
