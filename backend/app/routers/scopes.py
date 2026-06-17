from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.models import Scope, User
from app.schemas.schemas import ScopeCreate, ScopeOut, ScopeUpdate
from app.services.storage import storage

router = APIRouter(prefix="/scopes", tags=["scopes"])


@router.get("", response_model=list[ScopeOut])
def list_scopes(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Scope).order_by(Scope.created_at.desc()).all()


@router.post("", response_model=ScopeOut, status_code=201)
def create_scope(
    payload: ScopeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    scope = Scope(**payload.model_dump())
    db.add(scope)
    db.commit()
    db.refresh(scope)
    return scope


@router.patch("/{scope_id}", response_model=ScopeOut)
def update_scope(
    scope_id: int,
    payload: ScopeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    scope = db.get(Scope, scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Scope not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scope, field, value)
    db.commit()
    db.refresh(scope)
    return scope


@router.delete("/{scope_id}", status_code=204)
def delete_scope(
    scope_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    scope = db.get(Scope, scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Scope not found")
    # remove stored files, then the scope (cascade deletes attachment rows)
    for att in scope.attachments:
        storage.delete(att.storage_path)
    db.delete(scope)
    db.commit()
