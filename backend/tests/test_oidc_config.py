"""Runtime OIDC config (issue #11): secret-at-rest + DB-over-env resolution.

No live tenant or Postgres required — an in-memory SQLite session backs the
``oidc_settings`` row. ``get_settings()`` is lru_cached, so mutating the returned
object sets the env-fallback values the resolver reads.
"""

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import oidc
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.database import Base
from app.core.oidc_config import get_oidc_config
from app.models.models import OidcSettings


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def env_oidc():
    """Set deterministic env-fallback values and restore them afterwards."""
    s = get_settings()
    saved = {k: getattr(s, k) for k in (
        "oidc_enabled", "oidc_authority", "oidc_client_id", "oidc_client_secret",
        "oidc_scopes", "oidc_groups_claim",
    )}
    s.oidc_enabled = False
    s.oidc_authority = "https://env-authority/v2.0"
    s.oidc_client_id = "env-client"
    s.oidc_client_secret = "env-secret"
    s.oidc_scopes = "openid profile email"
    s.oidc_groups_claim = "groups"
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


def test_secret_round_trip():
    token = encrypt_secret("hunter2")
    assert token != "hunter2"  # actually encrypted
    assert decrypt_secret(token) == "hunter2"


def test_decrypt_rejects_tampered_token():
    with pytest.raises(InvalidToken):
        decrypt_secret("not-a-valid-fernet-token")


def test_empty_table_falls_back_to_env(db, env_oidc):
    cfg = get_oidc_config(db)
    assert cfg.enabled is False
    assert cfg.authority == "https://env-authority/v2.0"
    assert cfg.client_id == "env-client"
    assert cfg.client_secret == "env-secret"


def test_db_row_overrides_env_and_decrypts_secret(db, env_oidc):
    db.add(OidcSettings(
        id=1,
        enabled=True,
        authority="https://db-authority/v2.0",
        client_id="db-client",
        client_secret_enc=encrypt_secret("db-secret"),
    ))
    db.commit()

    cfg = get_oidc_config(db)
    assert cfg.enabled is True
    assert cfg.authority == "https://db-authority/v2.0"
    assert cfg.client_id == "db-client"
    assert cfg.client_secret == "db-secret"
    # Blank DB fields still fall back to env per-field.
    assert cfg.scopes == "openid profile email"
    assert cfg.groups_claim == "groups"


def test_blank_db_fields_fall_back_per_field(db, env_oidc):
    # enabled set, but authority left blank -> env authority wins.
    db.add(OidcSettings(id=1, enabled=True, authority="", client_id=""))
    db.commit()
    cfg = get_oidc_config(db)
    assert cfg.enabled is True
    assert cfg.authority == "https://env-authority/v2.0"
    assert cfg.client_id == "env-client"


def test_undecryptable_secret_falls_back_to_env(db, env_oidc):
    db.add(OidcSettings(id=1, enabled=True, client_secret_enc="corrupt-token"))
    db.commit()
    cfg = get_oidc_config(db)
    assert cfg.client_secret == "env-secret"  # did not blow up


def test_reset_caches_clears_discovery_and_jwks():
    oidc._discovery_cache["https://x/v2.0"] = (9e9, {"issuer": "x"})
    oidc._jwk_clients["https://x/jwks"] = object()
    oidc.reset_caches()
    assert oidc._discovery_cache == {}
    assert oidc._jwk_clients == {}
