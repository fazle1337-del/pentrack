"""Minimal, provider-agnostic OIDC Authorization Code client.

Talks the standard OpenID Connect contract (discovery + JWKS + auth-code), so
the same code works against Entra ID in production and Keycloak (or any OIDC
provider) in the home lab — only the authority changes. The flow ends by
handing validated claims back to the caller, which provisions a local user and
issues the app's own JWT; Entra tokens never reach the rest of the API.

The connection config (authority/client/secret/...) is resolved per-request from
``OidcConfig`` (DB-backed, runtime-editable — issue #11) and passed in, so there
is no import-time snapshot: changing the config in the admin UI takes effect on
the next login without a restart. The discovery/JWKS caches are keyed by
authority and can be cleared via :func:`reset_caches` when config is saved.

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
from app.core.oidc_config import OidcConfig

settings = get_settings()  # only for jwt_secret/algorithm (state token) — not OIDC


class OIDCError(Exception):
    """Raised on any discovery / token-exchange / validation failure."""


_DISCOVERY_TTL = 3600  # seconds
# Caches keyed by authority so a reconfigured tenant never serves stale metadata.
_discovery_cache: dict[str, tuple[float, dict]] = {}
_jwk_clients: dict[str, PyJWKClient] = {}


def reset_caches() -> None:
    """Drop cached discovery docs and JWKS clients. Call after the OIDC config
    changes so the next login refetches against the new authority."""
    _discovery_cache.clear()
    _jwk_clients.clear()


def _discovery(authority: str) -> dict:
    """Fetch and cache the provider's OpenID configuration document."""
    if not authority:
        raise OIDCError("OIDC authority is not configured")
    cached = _discovery_cache.get(authority)
    if cached and (time.time() - cached[0]) < _DISCOVERY_TTL:
        return cached[1]
    url = authority.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    doc = resp.json()
    _discovery_cache[authority] = (time.time(), doc)
    return doc


def _jwks(authority: str) -> PyJWKClient:
    """Cache a PyJWKClient bound to the provider's current jwks_uri."""
    uri = _discovery(authority)["jwks_uri"]
    client = _jwk_clients.get(uri)
    if client is None:
        client = PyJWKClient(uri)
        _jwk_clients[uri] = client
    return client


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


def build_authorization_url(cfg: OidcConfig, state: str, nonce: str) -> str:
    """Build the provider /authorize redirect URL for the auth-code flow."""
    disc = _discovery(cfg.authority)
    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "scope": cfg.scopes,
        "state": state,
        "nonce": nonce,
        "response_mode": "query",
    }
    return disc["authorization_endpoint"] + "?" + urlencode(params)


def exchange_code(cfg: OidcConfig, code: str) -> dict:
    """Exchange an authorization code for tokens at the provider's token endpoint."""
    disc = _discovery(cfg.authority)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    }
    resp = httpx.post(disc["token_endpoint"], data=data, timeout=10)
    if resp.status_code != 200:
        raise OIDCError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def validate_id_token(cfg: OidcConfig, id_token: str, nonce: str) -> dict:
    """Verify the id_token signature/issuer/audience and bind the nonce."""
    disc = _discovery(cfg.authority)
    signing_key = _jwks(cfg.authority).get_signing_key_from_jwt(id_token).key
    try:
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=cfg.client_id,
            issuer=disc["issuer"],
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise OIDCError(f"id_token validation failed: {exc}") from exc
    if claims.get("nonce") != nonce:
        raise OIDCError("nonce mismatch")
    return claims
