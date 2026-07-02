from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.models.enums import AuthType
from app.models.models import Finding, IdpRoleMap, Team, User
from app.schemas.schemas import (
    TeamCreate,
    TeamOut,
    TeamUpdate,
    UserCreate,
    UserOut,
)

router = APIRouter(tags=["teams-users"])


# ---- Teams ----
@router.get("/teams", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Team).order_by(Team.name).all()


@router.post("/teams", response_model=TeamOut, status_code=201)
def create_team(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.query(Team).filter(Team.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Team already exists")
    team = Team(name=payload.name)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.patch("/teams/{team_id}", response_model=TeamOut)
def update_team(
    team_id: int,
    payload: TeamUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Team name is required")
    clash = (
        db.query(Team)
        .filter(Team.name == name, Team.id != team_id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="Team already exists")
    team.name = name

    # ev_group_id: None (field omitted) = leave unchanged, so existing
    # rename-only callers can't accidentally wipe it. "" clears it explicitly
    # (stored as NULL, not "" — the unique index would otherwise collide
    # across every team that clears it).
    if payload.ev_group_id is not None:
        ev_group_id = payload.ev_group_id.strip() or None
        if ev_group_id:
            ev_clash = (
                db.query(Team)
                .filter(Team.ev_group_id == ev_group_id, Team.id != team_id)
                .first()
            )
            if ev_clash:
                raise HTTPException(
                    status_code=409,
                    detail=f"EasyVista group '{ev_group_id}' is already mapped "
                    f"to team '{ev_clash.name}'",
                )
        team.ev_group_id = ev_group_id

    db.commit()
    db.refresh(team)
    return team


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    # Block deletion while the team is still referenced — there's no FK cascade
    # for these and silently nulling them would lose ownership data. Report the
    # counts so the admin knows what to reassign first.
    findings = (
        db.query(Finding).filter(Finding.remediation_owner_team_id == team_id).count()
    )
    users = db.query(User).filter(User.team_id == team_id).count()
    maps = db.query(IdpRoleMap).filter(IdpRoleMap.team_id == team_id).count()
    if findings or users or maps:
        parts = []
        if findings:
            parts.append(f"{findings} finding(s)")
        if users:
            parts.append(f"{users} user(s)")
        if maps:
            parts.append(f"{maps} group mapping(s)")
        raise HTTPException(
            status_code=409,
            detail="Team is still referenced by " + ", ".join(parts)
            + ". Reassign them before deleting.",
        )
    db.delete(team)
    db.commit()
    return Response(status_code=204)


# ---- Users ----
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.name).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already in use")
    if payload.auth_type == AuthType.local and not payload.password:
        raise HTTPException(
            status_code=422, detail="Password required for local accounts"
        )
    user = User(
        name=payload.name,
        email=payload.email,
        auth_type=payload.auth_type,
        role=payload.role,
        team_id=payload.team_id,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
