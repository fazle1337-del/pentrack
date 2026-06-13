from functools import lru_cache
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

    # Entra ID (Phase 5 — stubbed)
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
