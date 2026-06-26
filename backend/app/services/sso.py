"""SSO group-to-role resolution and just-in-time user provisioning.

Given validated OIDC claims, look up the user's group identifiers in
``IdpRoleMap``, pick the highest-privilege role, and create or update the local
``User`` accordingly. A user whose groups map to no role is rejected — we never
silently create a privilege-less account.
"""

from sqlalchemy.orm import Session

from app.models.enums import AuthType, Role
from app.models.models import IdpRoleMap, User

# Higher number = more privilege. Keep in sync with the Role enum.
_ROLE_RANK = {Role.member: 1, Role.admin: 2}


class NoRoleMapped(Exception):
    """The user's groups matched no IdpRoleMap entry — login is denied."""


class LocalAccountConflict(Exception):
    """A local (break-glass) account already owns this email; SSO must not take
    it over. Raised so the break-glass credentials stay purely local."""


def _extract_groups(claims: dict, groups_claim: str) -> list[str]:
    groups = claims.get(groups_claim) or []
    if isinstance(groups, str):
        groups = [groups]
    return [str(g) for g in groups]


def resolve_and_provision(db: Session, claims: dict, groups_claim: str) -> User:
    """Map claims -> role and upsert the local user. Raises NoRoleMapped if the
    user has no group that grants a role."""
    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not email:
        raise ValueError("Token has no email/preferred_username claim")
    name = claims.get("name") or email

    groups = _extract_groups(claims, groups_claim)
    matches = (
        db.query(IdpRoleMap).filter(IdpRoleMap.idp_group_id.in_(groups)).all()
        if groups
        else []
    )
    if not matches:
        raise NoRoleMapped(email)

    # Highest-privilege match wins; carry its team assignment if it has one.
    best = max(matches, key=lambda m: _ROLE_RANK[m.role])
    team_id = next((m.team_id for m in matches if m.team_id is not None), None)

    user = db.query(User).filter(User.email == email).first()
    if user is not None and user.auth_type == AuthType.local:
        raise LocalAccountConflict(email)
    if user is None:
        user = User(name=name, email=email)
        db.add(user)
    user.auth_type = AuthType.sso
    user.role = best.role
    if team_id is not None:
        user.team_id = team_id
    user.is_active = True
    if not user.name:
        user.name = name

    db.commit()
    db.refresh(user)
    return user
