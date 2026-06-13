from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.models.enums import AuthType
from app.models.models import Team, User
from app.schemas.schemas import TeamCreate, TeamOut, UserCreate, UserOut

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
