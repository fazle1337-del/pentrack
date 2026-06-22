"""Admin CRUD for IdP group -> role mappings.

Lets an InfoSec admin point Entra group GUIDs (or Keycloak group paths) at app
roles from the UI/API instead of editing the database directly.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.enums import Role
from app.models.models import IdpRoleMap

router = APIRouter(prefix="/idp-role-maps", tags=["sso"])


class IdpRoleMapIn(BaseModel):
    idp_group_id: str
    label: str | None = None
    role: Role
    team_id: int | None = None


class IdpRoleMapOut(IdpRoleMapIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.get("", response_model=list[IdpRoleMapOut])
def list_maps(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(IdpRoleMap).order_by(IdpRoleMap.id).all()


@router.post("", response_model=IdpRoleMapOut, status_code=status.HTTP_201_CREATED)
def create_map(
    body: IdpRoleMapIn, db: Session = Depends(get_db), _=Depends(require_admin)
):
    if db.query(IdpRoleMap).filter_by(idp_group_id=body.idp_group_id).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A mapping for this group already exists"
        )
    m = IdpRoleMap(**body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_map(map_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    m = db.get(IdpRoleMap, map_id)
    if m is not None:
        db.delete(m)
        db.commit()
