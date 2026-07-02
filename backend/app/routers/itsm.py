"""Admin-triggered EasyVista (ITSM) push + a public config probe.

OFF by default: the push route 404s unless `easyvista_enabled` is set, mirroring
the SSO routes. Pushing is an explicit admin action (not automatic on finding
create), so nothing leaves the app until an operator opts in per finding — which
keeps the integration safe to ship before a live EasyVista tenant exists.

EV assignment is group-based (wiki "EasyVista integration — open questions",
Q2), so pushing requires the finding to be **team-owned** with that team mapped
to an EV group (`Team.ev_group_id`) — an individually-owned finding has no EV
group to route the ticket to. Blocked with a 409 rather than silently omitting
the assignment, so admins immediately see what needs fixing (assign a team,
or map the team's EV group) instead of a ticket landing unassigned in EV.

Comments (Phase B, 2026-07-02): read-only, cached, visible to admins + the
finding's owning team (`can_access_finding`, not `require_admin` — the push/
refresh-status routes above stay admin-only, but comments follow the wiki's
"visible to admins + owning team" decision). Synced on-demand only, never by
the background poller (`services/easyvista_poller.py` is untouched).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import can_access_finding, get_current_user, require_admin
from app.models.models import Finding, FindingItsmComment, Team, User
from app.schemas.schemas import ItsmCommentOut
from app.services import easyvista

settings = get_settings()
router = APIRouter(prefix="/itsm", tags=["itsm"])


@router.get("/config")
def itsm_config():
    """Public: lets the frontend decide whether to show the 'Push to EasyVista' button."""
    return {"itsm_enabled": settings.easyvista_enabled}


@router.get("/groups")
def list_ev_groups(_=Depends(require_admin)):
    """Admin-only: EV's group list, for mapping Team.ev_group_id (no dedicated
    UI yet — this is the backend piece the future Integrations tab will use)."""
    if not settings.easyvista_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="ITSM integration is not enabled"
        )
    try:
        return easyvista.list_groups()
    except easyvista.EasyVistaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/findings/{finding_id}/push")
def push_finding_to_itsm(
    finding_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if not settings.easyvista_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="ITSM integration is not enabled"
        )
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Finding not found")

    team = (
        db.get(Team, finding.remediation_owner_team_id)
        if finding.remediation_owner_team_id
        else None
    )
    if team is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This finding has no owning team, so there's no EasyVista "
            "group to assign the ticket to. Assign it to a team first.",
        )
    if not team.ev_group_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Team '{team.name}' has no EasyVista group mapped yet "
            "(Team.ev_group_id). Map it before raising a ticket.",
        )

    try:
        result = easyvista.push_finding(db, finding, ev_group_id=team.ev_group_id)
    except easyvista.EasyVistaError as exc:
        # Upstream/config failure — surface as a bad-gateway, not a 500.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"itsm_reference": result["reference"], "href": result["href"]}


@router.post("/findings/{finding_id}/refresh")
def refresh_finding_status(
    finding_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """On-demand status sync (complementing the background poller). Pulls the
    current STATUS_EN + closed state (from END_DATE_UT) and caches it on the
    finding."""
    if not settings.easyvista_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="ITSM integration is not enabled"
        )
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Finding not found")
    if not finding.itsm_reference:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This finding hasn't been pushed to EasyVista yet.",
        )

    try:
        result = easyvista.get_request_status(finding.itsm_reference, db)
    except easyvista.EasyVistaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    finding.itsm_status_label = result["status_label"]
    finding.itsm_closed = result["closed"]
    finding.itsm_synced_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(finding)
    return {
        "itsm_status_label": finding.itsm_status_label,
        "itsm_closed": finding.itsm_closed,
        "itsm_synced_at": finding.itsm_synced_at,
    }


def _get_pushed_finding_for(user: User, finding_id: int, db: Session) -> Finding:
    """Shared gating for the two comment routes below: enabled, exists,
    visible to this user (admins + owning team — same rule as finding
    access generally, per the wiki's "comments visible to admins + owning
    team" decision), and already pushed to EV."""
    if not settings.easyvista_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="ITSM integration is not enabled"
        )
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Finding not found")
    if not can_access_finding(user, finding):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorised for this finding")
    if not finding.itsm_reference:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This finding hasn't been pushed to EasyVista yet.",
        )
    return finding


@router.post("/findings/{finding_id}/comments/sync", response_model=list[ItsmCommentOut])
def sync_finding_comments(
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch the ticket's comment thread from EV and replace the local cache
    for this finding. On-demand only — comments are never background-polled
    (wiki "Polling design": actions are the expensive/chatty part)."""
    finding = _get_pushed_finding_for(user, finding_id, db)
    try:
        fetched = easyvista.get_request_comments(finding.itsm_reference, db)
    except easyvista.EasyVistaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db.query(FindingItsmComment).filter(FindingItsmComment.finding_id == finding.id).delete()
    for c in fetched:
        db.add(FindingItsmComment(finding_id=finding.id, **c))
    db.commit()

    return (
        db.query(FindingItsmComment)
        .filter(FindingItsmComment.finding_id == finding.id)
        .order_by(FindingItsmComment.id.desc())
        .all()
    )


@router.get("/findings/{finding_id}/comments", response_model=list[ItsmCommentOut])
def get_finding_comments(
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the locally cached comment thread (no EV call) — call the sync
    route first to populate/refresh it."""
    finding = _get_pushed_finding_for(user, finding_id, db)
    return (
        db.query(FindingItsmComment)
        .filter(FindingItsmComment.finding_id == finding.id)
        .order_by(FindingItsmComment.id.desc())
        .all()
    )
