from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from app.models.integration_config import IntegrationConfig

from app.integrations.base import IntegrationProvider, ProviderContext

_REGISTRY: dict[str, Type[IntegrationProvider]] = {}


def register(name: str):
    """Class decorator: registers a provider class under a provider name string."""

    def decorator(cls: Type[IntegrationProvider]) -> Type[IntegrationProvider]:
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_provider_class(name: str) -> Type[IntegrationProvider]:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown provider {name!r}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_providers() -> list[str]:
    return sorted(_REGISTRY.keys())


def build_provider(config: "IntegrationConfig") -> IntegrationProvider:
    """Decrypt credentials from an IntegrationConfig and return a ready-to-use provider."""
    import json

    from app.core.encryption import decrypt_token

    cls = get_provider_class(config.provider)

    access_token = (
        decrypt_token(config.access_token_encrypted) if config.access_token_encrypted else None
    )
    refresh_token = (
        decrypt_token(config.refresh_token_encrypted) if config.refresh_token_encrypted else None
    )

    # Non-OAuth credentials (e.g. CalDAV username/password stored as encrypted JSON)
    extra_config: dict = dict(config.config or {})
    if config.credentials_encrypted:
        try:
            creds_json = decrypt_token(config.credentials_encrypted)
            extra_config.update(json.loads(creds_json))
        except Exception:
            pass

    context = ProviderContext(
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=config.token_expires_at,
        extra_config=extra_config,
    )
    return cls(context)
