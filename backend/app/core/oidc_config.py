"""Resolve the *effective* OIDC connection config.

Single source of truth for the OIDC settings used by the auth-code flow. Reads
the runtime-editable ``oidc_settings`` row (issue #11) first and falls back to
the env/file values in ``Settings`` per field, so:

  - no row / blank field  -> env behaviour (existing deployments unchanged);
  - a configured field    -> the DB value wins.

The client secret is decrypted here; if decryption fails (e.g. ``APP_SEED`` was
rotated since it was saved) we fall back to the env secret rather than break SSO.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import InvalidToken, decrypt_secret
from app.models.models import OidcSettings

_ROW_ID = 1


@dataclass(frozen=True)
class OidcConfig:
    enabled: bool
    authority: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    groups_claim: str
    post_login_redirect: str


def get_oidc_settings_row(db: Session) -> OidcSettings | None:
    return db.get(OidcSettings, _ROW_ID)


def get_oidc_config(db: Session) -> OidcConfig:
    """Build the effective OIDC config (DB row over env, per field)."""
    s = get_settings()
    row = get_oidc_settings_row(db)

    def pick(attr: str, env_value: str) -> str:
        if row is not None:
            value = getattr(row, attr)
            if value:  # non-None and non-empty
                return value
        return env_value

    enabled = s.oidc_enabled
    if row is not None and row.enabled is not None:
        enabled = row.enabled

    secret = s.oidc_client_secret
    if row is not None and row.client_secret_enc:
        try:
            secret = decrypt_secret(row.client_secret_enc)
        except InvalidToken:
            secret = s.oidc_client_secret

    return OidcConfig(
        enabled=enabled,
        authority=pick("authority", s.oidc_authority),
        client_id=pick("client_id", s.oidc_client_id),
        client_secret=secret,
        redirect_uri=pick("redirect_uri", s.oidc_redirect_uri),
        scopes=pick("scopes", s.oidc_scopes),
        groups_claim=pick("groups_claim", s.oidc_groups_claim),
        post_login_redirect=pick("post_login_redirect", s.oidc_post_login_redirect),
    )
