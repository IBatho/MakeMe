from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # App
    APP_NAME: str = "MakeMe"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://makeme:makeme@localhost:5432/makeme"
    # Sync URL used only by Alembic (psycopg2)
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://makeme:makeme@localhost:5432/makeme"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Encryption key for integration credentials (Fernet — run generate_key.py to create)
    ENCRYPTION_KEY: str = "CHANGE_ME_generate_with_cryptography_fernet"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8081"]

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # OAuth — Notion
    NOTION_CLIENT_ID: str = ""
    NOTION_CLIENT_SECRET: str = ""

    # OAuth — Google Calendar
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # OAuth redirect base (backend URL that providers redirect back to)
    OAUTH_REDIRECT_BASE_URL: str = "http://localhost:8000"

    # Mobile deep-link scheme used after OAuth success
    MOBILE_DEEP_LINK_SCHEME: str = "makeme"

    # OAuth — Microsoft 365 / Graph API
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""

    # Anthropic API key for LLM advisor (Phase 5 — optional)
    ANTHROPIC_API_KEY: str = ""


settings = Settings()
