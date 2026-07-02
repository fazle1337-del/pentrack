"""Runtime EasyVista bearer-token config (2026-07-01 correction): secret-at-rest
+ DB-over-env resolution, and KDF-context isolation from the OIDC secret.

No live tenant or Postgres required — an in-memory SQLite session backs the
``easyvista_settings`` row, mirroring test_oidc_config.py's pattern.
"""

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.crypto import EASYVISTA_CONTEXT, OIDC_CONTEXT, decrypt_secret, encrypt_secret
from app.core.database import Base
from app.core.easyvista_config import get_easyvista_bearer_token
from app.models.models import EasyVistaSettings


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
def env_token():
    s = get_settings()
    saved = s.easyvista_bearer_token
    s.easyvista_bearer_token = "env-bearer-token"
    yield s
    s.easyvista_bearer_token = saved


def test_secret_round_trip_with_easyvista_context():
    token = encrypt_secret("hunter2", context=EASYVISTA_CONTEXT)
    assert token != "hunter2"
    assert decrypt_secret(token, context=EASYVISTA_CONTEXT) == "hunter2"


def test_easyvista_and_oidc_contexts_are_not_interchangeable():
    """The two secret types must use distinct KDF contexts so a value encrypted
    for one can never be decrypted as the other, even sharing the same
    jwt_secret."""
    token = encrypt_secret("hunter2", context=EASYVISTA_CONTEXT)
    with pytest.raises(InvalidToken):
        decrypt_secret(token, context=OIDC_CONTEXT)


def test_empty_table_falls_back_to_env(db, env_token):
    assert get_easyvista_bearer_token(db) == "env-bearer-token"


def test_db_row_overrides_env_and_decrypts_token(db, env_token):
    db.add(EasyVistaSettings(id=1, bearer_token_enc=encrypt_secret(
        "db-bearer-token", context=EASYVISTA_CONTEXT
    )))
    db.commit()
    assert get_easyvista_bearer_token(db) == "db-bearer-token"


def test_undecryptable_token_falls_back_to_env(db, env_token):
    db.add(EasyVistaSettings(id=1, bearer_token_enc="corrupt-token"))
    db.commit()
    assert get_easyvista_bearer_token(db) == "env-bearer-token"  # did not blow up


def test_blank_db_token_falls_back_to_env(db, env_token):
    db.add(EasyVistaSettings(id=1, bearer_token_enc=None))
    db.commit()
    assert get_easyvista_bearer_token(db) == "env-bearer-token"
