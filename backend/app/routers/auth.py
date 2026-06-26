import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core import oidc
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.oidc_config import get_oidc_config
from app.core.security import create_access_token, verify_password
from app.models.enums import AuthType
from app.models.models import User
from app.schemas.schemas import Token, UserOut
from app.services.sso import LocalAccountConflict, NoRoleMapped, resolve_and_provision

router = APIRouter(prefix="/auth", tags=["auth"])


def _sso_redirect(base: str, suffix: str) -> RedirectResponse:
    """Bounce back to the frontend, passing the result in the URL fragment so it
    never hits a server log. The SPA reads it on load (see consumeSsoRedirect)."""
    return RedirectResponse(
        f"{base or '/'}#{suffix}", status_code=status.HTTP_302_FOUND
    )


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if (
        user is None
        or user.auth_type != AuthType.local
        or not user.password_hash
        or not verify_password(form_data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled"
        )
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """Current user — the frontend uses this to gate admin-only UI."""
    return user


@router.get("/config")
def auth_config(db: Session = Depends(get_db)):
    """Public: lets the frontend decide whether to render the SSO button."""
    return {"sso_enabled": get_oidc_config(db).enabled}


@router.get("/sso/login")
def sso_login(db: Session = Depends(get_db)):
    """Kick off the OIDC auth-code flow by redirecting to the provider."""
    cfg = get_oidc_config(db)
    if not cfg.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="SSO is not enabled")
    nonce = secrets.token_urlsafe(16)
    state = oidc.create_state_token(nonce)
    return RedirectResponse(
        oidc.build_authorization_url(cfg, state, nonce),
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/sso/callback")
def sso_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Provider redirects here with an auth code; validate it, provision the
    user, and hand the SPA the app's own JWT."""
    cfg = get_oidc_config(db)
    if not cfg.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="SSO is not enabled")
    if error or not code or not state:
        return _sso_redirect(cfg.post_login_redirect, f"sso_error={error or 'login_failed'}")
    try:
        nonce = oidc.read_state_token(state)
        tokens = oidc.exchange_code(cfg, code)
        claims = oidc.validate_id_token(cfg, tokens["id_token"], nonce)
        user = resolve_and_provision(db, claims, cfg.groups_claim)
    except NoRoleMapped:
        return _sso_redirect(cfg.post_login_redirect, "sso_error=no_role")
    except LocalAccountConflict:
        # Break-glass: a local account with this email exists and is never
        # silently taken over by SSO.
        return _sso_redirect(cfg.post_login_redirect, "sso_error=local_account")
    except Exception:
        # Don't leak provider/validation internals to the browser.
        return _sso_redirect(cfg.post_login_redirect, "sso_error=login_failed")
    return _sso_redirect(cfg.post_login_redirect, f"sso_token={create_access_token(str(user.id))}")
