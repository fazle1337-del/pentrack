from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.models import Test, User
from app.schemas.schemas import TestCreate, TestOut, TestUpdate

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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(test, field, value)
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
