"""Admin CRUD for the runtime EasyVista bearer token + poller settings.

EV auth is a bearer token tied to a managed identity, not HTTP Basic (see
app/services/easyvista.py, 2026-07-01 correction). Mirrors oidc_config.py's
pattern: the token is **write-only** — accepted on PUT and stored encrypted
at rest, but never returned; the read endpoint only reports whether one is
set. Rotation is an admin action (request the technician rotate it in EV,
then re-enter it here), so it never needs a host-side file handoff.
Host/account/catalog/requestor stay env-configured
(docs/easyvista-integration.md) since only the token has a rotation lifecycle
an admin needs to manage without a redeploy.

The poll_* fields (locked decision: "admin-tab adjustable" intervals) are
**not** secret, so unlike the token they're stored plain and returned as-is —
`None`/omitted on PUT leaves them unchanged, same "don't wipe on partial
update" semantics as the token and Team.ev_group_id.

No frontend UI yet — that lands with the admin "Integrations" tab in a later
slice. This endpoint exists so the whole config surface is usable/testable
now, ahead of that UI.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.crypto import EASYVISTA_CONTEXT, encrypt_secret
from app.core.database import get_db
from app.core.deps import require_admin
from app.core.easyvista_config import (
    get_easyvista_bearer_token,
    get_easyvista_poll_config,
    get_easyvista_settings_row,
)
from app.models.models import EasyVistaSettings

router = APIRouter(prefix="/easyvista-config", tags=["itsm"])

_ROW_ID = 1


class EasyVistaConfigIn(BaseModel):
    # Write-only. None/"" => leave the stored token unchanged (typing nothing
    # must never wipe it). A non-empty value replaces it.
    bearer_token: str | None = None
    # None (field omitted) = leave unchanged, for all of the below.
    poll_enabled: bool | None = None
    poll_open_interval_seconds: int | None = None
    poll_closed_interval_seconds: int | None = None
    poll_closed_lookback_days: int | None = None


class EasyVistaConfigOut(BaseModel):
    """The token is never returned, only whether one is currently set. Poll
    settings are the effective (DB-over-env) values, not secret."""

    bearer_token_set: bool
    poll_enabled: bool
    poll_open_interval_seconds: int
    poll_closed_interval_seconds: int
    poll_closed_lookback_days: int


def _to_out(db: Session) -> EasyVistaConfigOut:
    poll = get_easyvista_poll_config(db)
    return EasyVistaConfigOut(
        bearer_token_set=bool(get_easyvista_bearer_token(db)),
        poll_enabled=poll.enabled,
        poll_open_interval_seconds=poll.open_interval_seconds,
        poll_closed_interval_seconds=poll.closed_interval_seconds,
        poll_closed_lookback_days=poll.closed_lookback_days,
    )


@router.get("", response_model=EasyVistaConfigOut)
def read_config(db: Session = Depends(get_db), _=Depends(require_admin)):
    return _to_out(db)


@router.put("", response_model=EasyVistaConfigOut)
def update_config(
    body: EasyVistaConfigIn, db: Session = Depends(get_db), _=Depends(require_admin)
):
    row = get_easyvista_settings_row(db)
    if row is None:
        row = EasyVistaSettings(id=_ROW_ID)
        db.add(row)

    if body.bearer_token:
        row.bearer_token_enc = encrypt_secret(body.bearer_token, context=EASYVISTA_CONTEXT)

    for attr in (
        "poll_enabled",
        "poll_open_interval_seconds",
        "poll_closed_interval_seconds",
        "poll_closed_lookback_days",
    ):
        value = getattr(body, attr)
        if value is not None:
            setattr(row, attr, value)

    db.commit()
    return _to_out(db)
