"""Minimal, provider-agnostic OIDC Authorization Code client.

Talks the standard OpenID Connect contract (discovery + JWKS + auth-code), so
the same code works against Entra ID in production and Keycloak (or any OIDC
provider) in the home lab — only ``oidc_authority`` changes. The flow ends by
handing validated claims back to the caller, which provisions a local user and
issues the app's own JWT; Entra tokens never reach the rest of the API.

State/nonce are carried statelessly: the nonce is signed into a short-lived JWT
(``create_state_token``) using the app secret and round-tripped as the OAuth
``state`` param, so no server-side session store is needed.
"""

import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings

settings = get_settings()


class OIDCError(Exception):
    """Raised on any discovery / token-exchange / validation failure."""


_discovery_cache: dict | None = None
_discovery_fetched_at: float = 0.0
_DISCOVERY_TTL = 3600  # seconds
_jwk_client: PyJWKClient | None = None
_jwk_client_uri: str | None = None


def _discovery() -> dict:
    """Fetch and cache the provider's OpenID configuration document."""
    global _discovery_cache, _discovery_fetched_at
    if _discovery_cache and (time.time() - _discovery_fetched_at) < _DISCOVERY_TTL:
        return _discovery_cache
    if not settings.oidc_authority:
        raise OIDCError("OIDC authority is not configured")
    url = settings.oidc_authority.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    _discovery_cache = resp.json()
    _discovery_fetched_at = time.time()
    return _discovery_cache


def _jwks() -> PyJWKClient:
    """Cache a PyJWKClient bound to the provider's current jwks_uri."""
    global _jwk_client, _jwk_client_uri
    uri = _discovery()["jwks_uri"]
    if _jwk_client is None or _jwk_client_uri != uri:
        _jwk_client = PyJWKClient(uri)
        _jwk_client_uri = uri
    return _jwk_client


def create_state_token(nonce: str) -> str:
    """Sign the nonce into a 10-minute state token (CSRF + nonce binding)."""
    payload = {
        "nonce": nonce,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def read_state_token(state: str) -> str:
    """Verify a state token and return the nonce it carries."""
    try:
        payload = jwt.decode(
            state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise OIDCError("Invalid or expired state") from exc
    return payload["nonce"]


def build_authorization_url(state: str, nonce: str) -> str:
    """Build the provider /authorize redirect URL for the auth-code flow."""
    disc = _discovery()
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": settings.oidc_scopes,
        "state": state,
        "nonce": nonce,
        "response_mode": "query",
    }
    return disc["authorization_endpoint"] + "?" + urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange an authorization code for tokens at the provider's token endpoint."""
    disc = _discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }
    resp = httpx.post(disc["token_endpoint"], data=data, timeout=10)
    if resp.status_code != 200:
        raise OIDCError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def validate_id_token(id_token: str, nonce: str) -> dict:
    """Verify the id_token signature/issuer/audience and bind the nonce."""
    disc = _discovery()
    signing_key = _jwks().get_signing_key_from_jwt(id_token).key
    try:
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=disc["issuer"],
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise OIDCError(f"id_token validation failed: {exc}") from exc
    if claims.get("nonce") != nonce:
        raise OIDCError("nonce mismatch")
    return claims
