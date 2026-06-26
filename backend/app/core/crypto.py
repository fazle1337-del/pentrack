"""Symmetric encryption for secrets stored at rest in the database.

Used for the OIDC client secret when SSO is configured from the admin UI
(issue #11). The key is *derived* from the app's ``jwt_secret`` — which on
Umbrel comes from ``${APP_SEED}`` — so no new secret has to be provisioned:
configuring SSO needs zero host-side file access, while a bare database dump is
useless without the env-held seed.

Caveat (documented, intentional): rotating ``jwt_secret`` / ``APP_SEED`` makes
the stored ciphertext undecryptable, so the client secret must be re-entered.
This mirrors the fact that rotating ``jwt_secret`` already invalidates every
issued session, so the blast radius is the same.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

# Context string so this key can never collide with any other use of jwt_secret.
_KDF_CONTEXT = b"pentrack-oidc-secret-v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(_KDF_CONTEXT + get_settings().jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns an opaque (Fernet) token string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt_secret`.

    Raises ``InvalidToken`` if the key has changed (e.g. ``APP_SEED`` rotated)
    or the stored value is corrupt; callers fall back to the env value.
    """
    return _fernet().decrypt(token.encode()).decode()


__all__ = ["encrypt_secret", "decrypt_secret", "InvalidToken"]
