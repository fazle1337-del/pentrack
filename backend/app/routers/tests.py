from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.models import Test, User
from app.schemas.schemas import TestCreate, TestOut, TestUpdate
from app.services.status_sync import sync_from_test

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("", response_model=list[TestOut])
def list_tests(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Test).order_by(Test.created_at.desc()).all()


@router.get("/{test_id}", response_model=TestOut)
def get_test(
    test_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    test = db.get(Test, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return test


@router.post("", response_model=TestOut, status_code=201)
def create_test(
    payload: TestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    test = Test(**payload.model_dump(), logged_by_user_id=user.id)
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.patch("/{test_id}", response_model=TestOut)
def update_test(
    test_id: int,
    payload: TestUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    test = db.get(Test, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    data = payload.model_dump(exclude_unset=True)
    status_changed = "status" in data and data["status"] != test.status
    ref_changed = (
        "unique_test_reference" in data
        and data["unique_test_reference"] != test.unique_test_reference
    )
    for field, value in data.items():
        setattr(test, field, value)
    if status_changed:
        test.status_updated_at = datetime.now(timezone.utc)
    if status_changed or ref_changed:
        sync_from_test(db, test)
    db.commit()
    db.refresh(test)
    return test


@router.delete("/{test_id}", status_code=204)
def delete_test(
    test_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    test = db.get(Test, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    db.delete(test)
    db.commit()
