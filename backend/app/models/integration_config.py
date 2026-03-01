import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class IntegrationConfig(Base, TimestampMixin):
    """
    Stores per-user configuration for each external integration provider.
    OAuth tokens and credentials are encrypted with Fernet before storage.
    """

    __tablename__ = "integration_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # e.g. "notion", "google_calendar", "apple_caldav", "microsoft_365"
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # "task_source", "calendar", or "both"
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))

    # OAuth tokens (Fernet-encrypted)
    access_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    oauth_scope: Mapped[str | None] = mapped_column(String(500))

    # Non-OAuth credentials (e.g. Notion internal integration token), Fernet-encrypted JSON
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)

    # Sync state
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(20))  # success, error, partial
    last_sync_error: Mapped[str | None] = mapped_column(String(1000))
    sync_cursor: Mapped[str | None] = mapped_column(String(1000))  # pagination delta token

    # Provider-specific config (e.g. notion_database_id, calendar_id)
    config: Mapped[dict | None] = mapped_column(JSONB)

    user = relationship("User", back_populates="integration_configs")
