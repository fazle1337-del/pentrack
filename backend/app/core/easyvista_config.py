"""Resolve effective EasyVista runtime config: DB over env, per field.

Mirrors app/core/oidc_config.py's pattern — host, account, catalog, and
requestor mail stay env-configured (docs/easyvista-integration.md); only the
bearer token (rotation lifecycle) and the poller settings (locked decision:
"admin-tab adjustable") are runtime-editable here.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import EASYVISTA_CONTEXT, InvalidToken, decrypt_secret
from app.models.models import EasyVistaSettings

_ROW_ID = 1


def get_easyvista_settings_row(db: Session) -> EasyVistaSettings | None:
    return db.get(EasyVistaSettings, _ROW_ID)


def get_easyvista_bearer_token(db: Session) -> str:
    """DB (decrypted) over env ``easyvista_bearer_token`` / ``_file``.

    Falls back to the env value if there's no row, no stored token, or
    decryption fails (e.g. APP_SEED rotated since it was saved) — never raises.
    """
    row = get_easyvista_settings_row(db)
    if row is not None and row.bearer_token_enc:
        try:
            return decrypt_secret(row.bearer_token_enc, context=EASYVISTA_CONTEXT)
        except InvalidToken:
            pass
    return get_settings().easyvista_bearer_token


@dataclass(frozen=True)
class EasyVistaPollConfig:
    enabled: bool
    open_interval_seconds: int
    closed_interval_seconds: int
    closed_lookback_days: int


def get_easyvista_poll_config(db: Session) -> EasyVistaPollConfig:
    """Build the effective poller config (DB row over env, per field)."""
    s = get_settings()
    row = get_easyvista_settings_row(db)

    enabled = s.easyvista_poll_enabled
    if row is not None and row.poll_enabled is not None:
        enabled = row.poll_enabled

    def pick_int(attr: str, env_value: int) -> int:
        if row is not None:
            value = getattr(row, attr)
            if value is not None and value > 0:
                return value
        return env_value

    return EasyVistaPollConfig(
        enabled=enabled,
        open_interval_seconds=pick_int(
            "poll_open_interval_seconds", s.easyvista_poll_open_interval_seconds
        ),
        closed_interval_seconds=pick_int(
            "poll_closed_interval_seconds", s.easyvista_poll_closed_interval_seconds
        ),
        closed_lookback_days=pick_int(
            "poll_closed_lookback_days", s.easyvista_poll_closed_lookback_days
        ),
    )
