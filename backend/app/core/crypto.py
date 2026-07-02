"""Symmetric encryption for secrets stored at rest in the database.

Used for the OIDC client secret (issue #11) and the EasyVista bearer token
(2026-07-01) when configured from the admin UI. The key is *derived* from the
app's ``jwt_secret`` — which on Umbrel comes from ``${APP_SEED}`` — so no new
secret has to be provisioned: configuring either integration needs zero
host-side file access, while a bare database dump is useless without the
env-held seed.

Each secret type uses its own KDF context string (``OIDC_CONTEXT`` /
``EASYVISTA_CONTEXT``) so the two derived keys can never collide, even though
they share the same underlying ``jwt_secret``.

Caveat (documented, intentional): rotating ``jwt_secret`` / ``APP_SEED`` makes
every stored ciphertext undecryptable, so secrets must be re-entered. This
mirrors the fact that rotating ``jwt_secret`` already invalidates every issued
session, so the blast radius is the same.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

# Context strings so each secret's key can never collide with another's, even
# though both are derived from the same jwt_secret.
OIDC_CONTEXT = b"pentrack-oidc-secret-v1:"
EASYVISTA_CONTEXT = b"pentrack-easyvista-secret-v1:"


def _fernet(context: bytes) -> Fernet:
    digest = hashlib.sha256(context + get_settings().jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, *, context: bytes = OIDC_CONTEXT) -> str:
    """Encrypt a secret for storage. Returns an opaque (Fernet) token string."""
    return _fernet(context).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, *, context: bytes = OIDC_CONTEXT) -> str:
    """Decrypt a token produced by :func:`encrypt_secret` (same ``context``).

    Raises ``InvalidToken`` if the key has changed (e.g. ``APP_SEED`` rotated)
    or the stored value is corrupt; callers fall back to the env value.
    """
    return _fernet(context).decrypt(token.encode()).decode()


__all__ = ["encrypt_secret", "decrypt_secret", "InvalidToken", "OIDC_CONTEXT", "EASYVISTA_CONTEXT"]
