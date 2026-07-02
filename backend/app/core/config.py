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

    # Login rate limiting (issue #6): throttle /auth/login per client IP to blunt
    # online brute-force / credential stuffing. In-process fixed-window counter
    # (slowapi) — no Redis, so it fits the single-instance Umbrel deployment.
    login_rate_limit_enabled: bool = True
    login_rate_limit: str = "10/minute"

    # CORS: comma-separated list of allowed browser origins (e.g.
    # "https://pentrack.example.com"). Empty = no cross-origin access, which is
    # the right default: the SPA is served same-origin and reaches the API
    # through the nginx /api proxy, so it needs no CORS at all. Set this only if a
    # separate-origin client must call the API directly. Credentials are never
    # allowed (auth is a Bearer header, not cookies).
    cors_allow_origins: str = ""

    # Interactive API docs (/api/docs, /api/redoc, /api/openapi.json). OFF by
    # default so the full API surface isn't disclosed on an internet-facing
    # instance; turn on in dev/local to use Swagger UI.
    api_docs_enabled: bool = False

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

    # EasyVista (ITSM) integration.
    # Pushes a finding into EasyVista Service Manager as a request/incident and
    # stores the returned reference on the finding's itsm_reference. OPTIONAL and
    # OFF by default — mirrors the SSO rollout: the code ships dark and is
    # validated against a real tenant later. The create-request contract is at
    # https://docs.easyvista.com/docs/rest-api-create-an-incident-request
    easyvista_enabled: bool = False
    easyvista_host: str = ""            # e.g. https://<account>.easyvista.com
    easyvista_account: str = ""         # the path segment in /api/v1/<account>/requests
    # REST auth (2026-07-01 correction, confirmed by the EV technician): a
    # bearer token tied to a managed EV identity — NOT HTTP Basic, which was
    # this scaffold's original (wrong) assumption. The token is normally set
    # via the admin UI (encrypted at rest — see app/core/easyvista_config.py),
    # which wins over these env fields; they're the pre-admin-UI/bootstrap
    # fallback, same relationship oidc_client_secret has to oidc_client_secret_file.
    easyvista_bearer_token: str = ""
    # File-based token (Docker-secret style); wins over the env var when the
    # file exists — same pattern as oidc_client_secret_file. Never commit secrets.
    easyvista_bearer_token_file: str = ""
    # Tenant-specific "subject" that classifies the created request. The API
    # REQUIRES one of these (guid preferred); values come from the EV catalogue.
    easyvista_catalog_guid: str = ""
    easyvista_catalog_code: str = ""
    # Requestor/recipient stamped on created requests. EV returns 406 if missing
    # or its email domain is unknown to the tenant — default to a known mailbox.
    easyvista_requestor_mail: str = ""
    # HTTP client timeout (EV's own server-side timeout defaults to 60s).
    easyvista_timeout_seconds: int = 30

    # Background status poller (locked decision: two poll intervals + on-demand
    # refresh, all admin-tab adjustable — DB-over-env resolution lives in
    # app/core/easyvista_config.py, same pattern as the bearer token but these
    # aren't secret so they're stored plain). OFF by default — even with
    # easyvista_enabled, an admin must separately opt into automatic polling,
    # matching this whole integration's "ships dark" default. Defaults mirror
    # the EV technician's suggestion: poll open tickets ~daily, closed tickets
    # weekly, and stop re-polling a ticket that's been closed for a year+.
    easyvista_poll_enabled: bool = False
    easyvista_poll_tick_seconds: int = 300  # how often the loop wakes to check what's due
    easyvista_poll_open_interval_seconds: int = 86400
    easyvista_poll_closed_interval_seconds: int = 604800
    easyvista_poll_closed_lookback_days: int = 365


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # File-based secret wins over the env var when present (Docker-secret style).
    if settings.oidc_client_secret_file:
        path = Path(settings.oidc_client_secret_file)
        if path.is_file():
            settings.oidc_client_secret = path.read_text().strip()
    if settings.easyvista_bearer_token_file:
        path = Path(settings.easyvista_bearer_token_file)
        if path.is_file():
            settings.easyvista_bearer_token = path.read_text().strip()
    return settings
