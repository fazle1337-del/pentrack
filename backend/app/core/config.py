from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://pentrack:pentrack@db:5432/pentrack"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Seed admin (created on startup if no users exist)
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "changeme"
    seed_admin_name: str = "InfoSec Admin"

    # Storage
    attachments_dir: str = "/data/attachments"

    # OIDC / Entra ID SSO.
    # The app authenticates against any OIDC provider (Entra in prod, Keycloak
    # in the home lab) and then issues its OWN app JWT, so the rest of the API
    # is unchanged. Only the authority URL differs between environments.
    oidc_enabled: bool = False
    oidc_authority: str = ""        # discovery base, e.g.
                                    # https://login.microsoftonline.com/<tenant-id>/v2.0
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    # Read the client secret from a file instead of the env var, so it never
    # has to live in a committed compose. Takes precedence when the file exists.
    # On Umbrel, point this at a file under the app's persistent data dir.
    oidc_client_secret_file: str = ""
    oidc_redirect_uri: str = ""     # must match the IdP app registration, e.g.
                                    # https://pentrack.example.com/api/auth/sso/callback
    oidc_scopes: str = "openid profile email"
    oidc_groups_claim: str = "groups"   # token claim holding group identifiers
                                        # (object-ID GUIDs in Entra; group paths in Keycloak)
    oidc_post_login_redirect: str = "/"  # frontend URL to land on after SSO

    # Non-prod convenience: seed two IdpRoleMap rows on first boot so a fresh
    # Keycloak realm works without manually creating mappings. Leave blank in prod.
    oidc_bootstrap_admin_group: str = ""
    oidc_bootstrap_member_group: str = ""


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # File-based secret wins over the env var when present (Docker-secret style).
    if settings.oidc_client_secret_file:
        path = Path(settings.oidc_client_secret_file)
        if path.is_file():
            settings.oidc_client_secret = path.read_text().strip()
    return settings
