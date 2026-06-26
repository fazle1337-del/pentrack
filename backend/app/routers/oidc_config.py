"""Admin CRUD for the runtime OIDC/Entra connection (issue #11).

Lets an InfoSec admin enable and configure SSO from the UI — authority, client
id, redirect, scopes, groups claim, and the client secret — instead of editing
compose env, bind-mounting a secret file, and recreating the container.

The client secret is **write-only**: it is accepted on ``PUT`` (and stored
encrypted at rest), but never returned; the read endpoint only reports whether
one is set. Saving invalidates the discovery/JWKS caches so the next login uses
the new config without a restart. Break-glass local login is independent of this,
so a bad config can always be fixed.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import oidc
from app.core.crypto import encrypt_secret
from app.core.database import get_db
from app.core.deps import require_admin
from app.core.oidc_config import get_oidc_config, get_oidc_settings_row
from app.models.models import OidcSettings

router = APIRouter(prefix="/oidc-config", tags=["sso"])

_ROW_ID = 1


class OidcConfigIn(BaseModel):
    enabled: bool | None = None
    authority: str | None = None
    client_id: str | None = None
    # Write-only. None/"" => leave the stored secret unchanged (typing nothing
    # must never wipe it). A non-empty value replaces it.
    client_secret: str | None = None
    redirect_uri: str | None = None
    scopes: str | None = None
    groups_claim: str | None = None
    post_login_redirect: str | None = None


class OidcConfigOut(BaseModel):
    """Effective config (DB over env), with the secret reduced to a flag."""

    enabled: bool
    authority: str
    client_id: str
    redirect_uri: str
    scopes: str
    groups_claim: str
    post_login_redirect: str
    client_secret_set: bool


def _to_out(db: Session) -> OidcConfigOut:
    cfg = get_oidc_config(db)
    return OidcConfigOut(
        enabled=cfg.enabled,
        authority=cfg.authority,
        client_id=cfg.client_id,
        redirect_uri=cfg.redirect_uri,
        scopes=cfg.scopes,
        groups_claim=cfg.groups_claim,
        post_login_redirect=cfg.post_login_redirect,
        client_secret_set=bool(cfg.client_secret),
    )


@router.get("", response_model=OidcConfigOut)
def read_config(db: Session = Depends(get_db), _=Depends(require_admin)):
    return _to_out(db)


@router.put("", response_model=OidcConfigOut)
def update_config(
    body: OidcConfigIn, db: Session = Depends(get_db), _=Depends(require_admin)
):
    row = get_oidc_settings_row(db)
    if row is None:
        row = OidcSettings(id=_ROW_ID)
        db.add(row)

    # Text/bool fields: store as given (blank string => falls back to env on read).
    for attr in (
        "enabled",
        "authority",
        "client_id",
        "redirect_uri",
        "scopes",
        "groups_claim",
        "post_login_redirect",
    ):
        value = getattr(body, attr)
        if value is not None:
            setattr(row, attr, value)

    # Secret: only touch it when a non-empty value is supplied.
    if body.client_secret:
        row.client_secret_enc = encrypt_secret(body.client_secret)

    db.commit()
    # New authority/secret must take effect on the next login.
    oidc.reset_caches()
    return _to_out(db)
