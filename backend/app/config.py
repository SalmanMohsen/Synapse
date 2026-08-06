from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://synapse:synapse@postgres:5432/synapse"    
    # Redis
    redis_url: str = "redis://redis:6379"

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Cookies
    cookie_secure: bool = False   # set True in production (HTTPS only)

    # CORS / OAuth redirects — must be the exact browser-facing frontend origin
    frontend_url: str = "http://localhost:5173"
    backend_url: str = ""

    # GitHub OAuth App credentials
    github_client_id: str = ""
    github_client_secret: str = ""

    # Google OAuth credentials
    google_client_id: str = ""
    google_client_secret: str = ""

    # GitHub App credentials (repository integration)
    github_app_id: str = ""
    github_app_slug: str = "synapse"  # Added slug field for installation URLs
    github_app_private_key_base64: str = ""  # base64-encoded PEM private key
    github_webhook_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()