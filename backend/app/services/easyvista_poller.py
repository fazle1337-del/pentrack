"""In-process background poller for EasyVista status sync.

Locked decision: two poll intervals (open vs closed ticket) + on-demand
refresh, all admin-tab adjustable; poller is in-process (no external
scheduler/store, so it works the same on single-instance Umbrel and Azure
ACR) — matches the pattern already used for login rate limiting
(app/core/ratelimit.py).

Scope: polls every finding pentrack already knows about (has
`itsm_reference` set, from a prior push). Does **not** poll EV globally by
ticket category to discover tickets pentrack doesn't know about yet (the
technician's stretch suggestion, wiki "Polling design") — that needs a
"list requests by category" EV endpoint that isn't confirmed/built.

Efficiency note: each due finding gets its own short-lived httpx.Client (via
`easyvista.get_request_status`'s default `client=None` path) rather than one
client reused across the whole pass. Fine at pentrack's expected finding
counts; revisit if a tenant has enough EV-pushed findings for this to matter.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.easyvista_config import get_easyvista_poll_config
from app.models.models import Finding
from app.services import easyvista

logger = logging.getLogger(__name__)


def _as_aware_utc(dt: datetime) -> datetime:
    """Some drivers (SQLite in tests; possibly others) don't round-trip
    tzinfo on a DateTime(timezone=True) column even though Postgres does —
    this code always writes UTC, so treat a naive value as UTC rather than
    let it blow up comparing against an aware `now`."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _is_due(
    finding: Finding,
    *,
    now: datetime,
    open_interval: timedelta,
    closed_interval: timedelta,
    lookback_cutoff: datetime,
) -> bool:
    """Whether `finding` is due for a status refresh this tick.

    Never synced -> always due (first-ever poll). Closed and last synced
    before `lookback_cutoff` -> never due again (bounded re-polling of old
    closed tickets, per the technician's suggestion). Otherwise due once its
    open/closed interval has elapsed since the last sync.
    """
    if finding.itsm_synced_at is None:
        return True
    synced_at = _as_aware_utc(finding.itsm_synced_at)
    if finding.itsm_closed is True:
        if synced_at < lookback_cutoff:
            return False
        interval = closed_interval
    else:
        interval = open_interval
    return now - synced_at >= interval


def poll_once(db: Session) -> int:
    """One polling pass over every pushed finding. Returns the number
    refreshed. No-ops (returns 0) if polling isn't enabled — safe to call
    unconditionally from the loop."""
    config = get_easyvista_poll_config(db)
    if not config.enabled:
        return 0

    now = datetime.now(timezone.utc)
    lookback_cutoff = now - timedelta(days=config.closed_lookback_days)
    open_interval = timedelta(seconds=config.open_interval_seconds)
    closed_interval = timedelta(seconds=config.closed_interval_seconds)

    findings = db.query(Finding).filter(Finding.itsm_reference.isnot(None)).all()
    refreshed = 0
    for finding in findings:
        if not _is_due(
            finding,
            now=now,
            open_interval=open_interval,
            closed_interval=closed_interval,
            lookback_cutoff=lookback_cutoff,
        ):
            continue
        try:
            result = easyvista.get_request_status(finding.itsm_reference, db)
        except easyvista.EasyVistaError:
            logger.warning(
                "EasyVista poll failed for finding %s (%s)",
                finding.id,
                finding.itsm_reference,
                exc_info=True,
            )
            continue
        finding.itsm_status_label = result["status_label"]
        finding.itsm_closed = result["closed"]
        finding.itsm_synced_at = now
        refreshed += 1

    if refreshed:
        db.commit()
    return refreshed
