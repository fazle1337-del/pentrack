from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import Role
from app.models.models import Finding, FindingReassignment, Test, User
from app.schemas.schemas import FindingCreate, FindingOut, FindingUpdate
from app.services.sla import compute_sla_status

router = APIRouter(prefix="/findings", tags=["findings"])

# Fields only InfoSec admins may change.
ADMIN_ONLY_FIELDS = {
    "gross_risk_rating",
    "net_likelihood",
    "net_impact",
    "net_rating",
    "net_risk_rationale",
    "remediation_owner_user_id",
    "remediation_owner_team_id",
}


def _serialize(finding: Finding) -> FindingOut:
    # Attach the computed (non-persisted) field so from_attributes can read it.
    finding.sla_status = compute_sla_status(finding.due_date, finding.status)
    return FindingOut.model_validate(finding)


def _can_access(user: User, finding: Finding) -> bool:
    if user.role == Role.admin:
        return True
    if finding.remediation_owner_user_id == user.id:
        return True
    if (
        user.team_id is not None
        and finding.remediation_owner_team_id is not None
        and finding.remediation_owner_team_id == user.team_id
    ):
        return True
    return False


@router.get("", response_model=list[FindingOut])
def list_findings(
    test_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Finding)
    if test_id is not None:
        query = query.filter(Finding.test_id == test_id)
    if user.role != Role.admin:
        # Members see only findings owned by them or their team.
        clauses = [Finding.remediation_owner_user_id == user.id]
        if user.team_id is not None:
            clauses.append(Finding.remediation_owner_team_id == user.team_id)
        query = query.filter(or_(*clauses))
    return [_serialize(f) for f in query.order_by(Finding.created_at.desc()).all()]


@router.get("/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if not _can_access(user, finding):
        raise HTTPException(status_code=403, detail="Not authorised for this finding")
    return _serialize(finding)


@router.post("", response_model=FindingOut, status_code=201)
def create_finding(
    payload: FindingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    if not db.get(Test, payload.test_id):
        raise HTTPException(status_code=404, detail="Test not found")
    finding = Finding(**payload.model_dump())
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return _serialize(finding)


@router.patch("/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: int,
    payload: FindingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if not _can_access(user, finding):
        raise HTTPException(status_code=403, detail="Not authorised for this finding")

    updates = payload.model_dump(exclude_unset=True)

    # Members cannot edit admin-only fields.
    if user.role != Role.admin:
        blocked = ADMIN_ONLY_FIELDS & updates.keys()
        if blocked:
            raise HTTPException(
                status_code=403,
                detail=f"Not permitted to edit: {', '.join(sorted(blocked))}",
            )

    # Record reassignment history when owner changes (admin only path).
    reassigning = (
        "remediation_owner_user_id" in updates
        or "remediation_owner_team_id" in updates
    )
    if reassigning:
        db.add(
            FindingReassignment(
                finding_id=finding.id,
                from_user_id=finding.remediation_owner_user_id,
                from_team_id=finding.remediation_owner_team_id,
                to_user_id=updates.get(
                    "remediation_owner_user_id", finding.remediation_owner_user_id
                ),
                to_team_id=updates.get(
                    "remediation_owner_team_id", finding.remediation_owner_team_id
                ),
                changed_by=user.id,
            )
        )

    for field, value in updates.items():
        setattr(finding, field, value)
    db.commit()
    db.refresh(finding)
    return _serialize(finding)


@router.delete("/{finding_id}", status_code=204)
def delete_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    db.delete(finding)
    db.commit()
