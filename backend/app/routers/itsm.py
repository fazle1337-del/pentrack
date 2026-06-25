"""Admin-triggered EasyVista (ITSM) push + a public config probe.

OFF by default: the push route 404s unless `easyvista_enabled` is set, mirroring
the SSO routes. Pushing is an explicit admin action (not automatic on finding
create), so nothing leaves the app until an operator opts in per finding — which
keeps the integration safe to ship before a live EasyVista tenant exists.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import require_admin
from app.models.models import Finding
from app.services import easyvista

settings = get_settings()
router = APIRouter(prefix="/itsm", tags=["itsm"])


@router.get("/config")
def itsm_config():
    """Public: lets the frontend decide whether to show the 'Push to EasyVista' button."""
    return {"itsm_enabled": settings.easyvista_enabled}


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
    try:
        result = easyvista.push_finding(db, finding)
    except easyvista.EasyVistaError as exc:
        # Upstream/config failure — surface as a bad-gateway, not a 500.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"itsm_reference": result["reference"], "href": result["href"]}
