from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class NormalisedTask:
    """Provider-agnostic task representation returned by fetch_tasks()."""

    source_id: str
    title: str
    description: str | None = None
    priority: str = "want"           # "need" | "want" | "like"
    total_duration_minutes: int = 60
    min_block_minutes: int = 30
    max_block_minutes: int = 120
    deadline: date | None = None
    window_start: date | None = None
    window_end: date | None = None
    is_complete: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class NormalisedEvent:
    """Provider-agnostic event representation returned by fetch_events()."""

    source_id: str
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None
    is_all_day: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class TokenData:
    """Returned by exchange_code() and refresh_access_token()."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class ProviderContext:
    """Decrypted credentials + provider-specific config passed to each provider."""

    access_token: str | None
    refresh_token: str | None
    token_expires_at: datetime | None
    extra_config: dict  # e.g. {"database_id": "...", "calendar_id": "..."}


class IntegrationProvider(ABC):
    """Abstract base class all integration providers must implement."""

    def __init__(self, context: ProviderContext) -> None:
        self.ctx = context

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_type(self) -> str: ...  # "task_source" | "calendar" | "both"

    # ── Tasks ────────────────────────────────────────────────────────────────

    async def fetch_tasks(self) -> list[NormalisedTask]:
        return []

    # ── Events ───────────────────────────────────────────────────────────────

    async def fetch_events(self, start: datetime, end: datetime) -> list[NormalisedEvent]:
        return []

    async def create_event(self, event: NormalisedEvent) -> str:
        raise NotImplementedError(f"{self.provider_name} does not support creating events")

    async def update_event(self, provider_event_id: str, event: NormalisedEvent) -> None:
        raise NotImplementedError(f"{self.provider_name} does not support updating events")

    async def delete_event(self, provider_event_id: str) -> None:
        raise NotImplementedError(f"{self.provider_name} does not support deleting events")

    # ── OAuth ────────────────────────────────────────────────────────────────

    @classmethod
    @abstractmethod
    def get_oauth_url(cls, state: str, redirect_uri: str) -> str: ...

    @classmethod
    @abstractmethod
    async def exchange_code(cls, code: str, redirect_uri: str) -> TokenData: ...

    async def refresh_access_token(self) -> TokenData:
        raise NotImplementedError(f"{self.provider_name} does not support token refresh")
