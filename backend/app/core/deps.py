from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.enums import Role
from app.models.models import Finding, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None or payload.get("sub") is None:
        raise credentials_exc
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise credentials_exc
    # Reject tokens issued before the user's current token_version (issue #5).
    # NULL/legacy values are treated as 0 on both sides.
    if int(payload.get("tv") or 0) != int(user.token_version or 0):
        raise credentials_exc
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user


def can_access_finding(user: User, finding: Finding) -> bool:
    """Shared finding-visibility rule: admins see everything; a member sees a
    finding only if they own it directly or via their team. Used by
    routers/findings.py (the finding CRUD routes) and routers/itsm.py (ITSM
    status/comments, which follow the same "admins + owning team" visibility
    per the wiki's locked EasyVista design decisions)."""
    if user.role == Role.admin:
        return True
    if finding.remediation_owner_user_id == user.id:
        return True
    return (
        user.team_id is not None
        and finding.remediation_owner_team_id == user.team_id
    )
