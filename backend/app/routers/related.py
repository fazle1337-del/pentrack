from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import Role
from app.models.models import Booking, Finding, Scope, Test, User

router = APIRouter(prefix="/related", tags=["related"])


@router.get("")
def get_related(
    ref: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Every entity that shares a ``unique_test_reference`` with ``ref``.

    The reference is the only link between tests, findings (via their test),
    BAU bookings and scopes — there is no hard FK — so a value can legitimately
    match several rows of the same type. We return all matches, flat, each item
    carrying the ``type``/``id`` the frontend needs to open its drawer. Finding
    visibility honours the same RBAC as ``GET /findings``.
    """
    ref = (ref or "").strip()
    items: list[dict] = []
    if not ref:
        return items

    tests = db.query(Test).filter(Test.unique_test_reference == ref).all()
    for t in tests:
        items.append(
            {"type": "test", "id": t.id, "label": t.name, "sub": t.status.value if t.status else None}
        )

    test_ids = [t.id for t in tests]
    if test_ids:
        fq = db.query(Finding).filter(Finding.test_id.in_(test_ids))
        if user.role != Role.admin:
            clauses = [Finding.remediation_owner_user_id == user.id]
            if user.team_id is not None:
                clauses.append(Finding.remediation_owner_team_id == user.team_id)
            fq = fq.filter(or_(*clauses))
        for f in fq.all():
            items.append(
                {
                    "type": "finding",
                    "id": f.id,
                    "label": f.vulnerability or "Untitled finding",
                    "sub": f.status.value if f.status else None,
                }
            )

    for b in db.query(Booking).filter(Booking.unique_test_reference == ref).all():
        items.append(
            {"type": "booking", "id": b.id, "label": b.title, "sub": b.status.value if b.status else None}
        )

    for s in db.query(Scope).filter(Scope.unique_test_reference == ref).all():
        items.append({"type": "scope", "id": s.id, "label": s.title, "sub": None})

    return items
