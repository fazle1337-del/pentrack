"""Two-way status sync between a Test and its schedule Bookings, matched by the
shared ``unique_test_reference`` string.

Rule (agreed in the spec): the test and its *most-recently-updated* booking stay
in lockstep; other bookings (reschedules, cancellations) keep their own status.

- A booking's status change mirrors onto the matching test.
- A test's status change mirrors onto its most-recently-updated matching booking.

Callers set the changed entity's ``status_updated_at`` and then call the matching
helper; the helper stamps the entity it propagates to as well.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Booking, Test


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ref(value: str | None) -> str | None:
    v = (value or "").strip()
    return v or None


def sync_from_booking(db: Session, booking: Booking) -> None:
    """Booking status changed -> mirror onto any test sharing its reference."""
    ref = _ref(booking.unique_test_reference)
    if not ref:
        return
    for test in db.query(Test).filter(Test.unique_test_reference == ref).all():
        if test.status != booking.status:
            test.status = booking.status
            test.status_updated_at = _now()


def sync_from_test(db: Session, test: Test) -> None:
    """Test status changed -> mirror onto its most-recently-updated booking."""
    ref = _ref(test.unique_test_reference)
    if not ref:
        return
    bookings = db.query(Booking).filter(Booking.unique_test_reference == ref).all()
    if not bookings:
        return
    latest = max(
        bookings,
        key=lambda b: (b.status_updated_at or b.created_at or datetime.min.replace(tzinfo=timezone.utc)),
    )
    if latest.status != test.status:
        latest.status = test.status
        latest.status_updated_at = _now()
