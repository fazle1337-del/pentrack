from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.models import Booking, User
from app.schemas.schemas import BookingCreate, BookingOut, BookingReorder, BookingUpdate
from app.services.status_sync import sync_from_booking

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("", response_model=list[BookingOut])
def list_bookings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Booking).order_by(Booking.sort_order, Booking.start_at).all()


@router.post("", response_model=BookingOut, status_code=201)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if payload.end_at < payload.start_at:
        raise HTTPException(status_code=422, detail="end_at must be on or after start_at")
    max_order = db.query(func.max(Booking.sort_order)).scalar()
    booking = Booking(
        **payload.model_dump(),
        status_updated_at=_now(),
        sort_order=(max_order or 0) + 1,
    )
    db.add(booking)
    sync_from_booking(db, booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: int,
    payload: BookingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    data = payload.model_dump(exclude_unset=True)
    status_changed = "status" in data and data["status"] != booking.status
    ref_changed = (
        "unique_test_reference" in data
        and data["unique_test_reference"] != booking.unique_test_reference
    )
    for field, value in data.items():
        setattr(booking, field, value)
    if booking.end_at < booking.start_at:
        raise HTTPException(status_code=422, detail="end_at must be on or after start_at")
    if status_changed:
        booking.status_updated_at = _now()
    if status_changed or ref_changed:
        sync_from_booking(db, booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.delete("/{booking_id}", status_code=204)
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    db.delete(booking)
    db.commit()


@router.post("/reorder", status_code=204)
def reorder_bookings(
    payload: BookingReorder,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Rewrite the global row order from the given list of booking ids."""
    for idx, booking_id in enumerate(payload.ordered_ids):
        booking = db.get(Booking, booking_id)
        if booking:
            booking.sort_order = idx
    db.commit()
