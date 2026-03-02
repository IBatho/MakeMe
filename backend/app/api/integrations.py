"""
Integration API router.

Endpoints
─────────
GET    /integrations                        list user's integrations
POST   /integrations                        connect via internal token (Notion secret)
GET    /integrations/{id}                   get one integration
PATCH  /integrations/{id}                   update display_name / config / is_enabled
DELETE /integrations/{id}                   disconnect (delete) an integration
POST   /integrations/{id}/sync              trigger immediate sync
GET    /integrations/oauth/{provider}/url   get OAuth redirect URL  (auth required)
GET    /integrations/oauth/{provider}/callback  handle OAuth callback  (no auth — browser redirect)
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.encryption import encrypt_token
from app.integrations.registry import build_provider, get_provider_class, list_providers
from app.models.integration_config import IntegrationConfig
from app.models.user import User
from app.schemas.integration import (
    CalDAVConnectBody,
    IntegrationCreate,
    IntegrationResponse,
    IntegrationUpdate,
    OAuthUrlResponse,
    SyncResult,
)
from app.services.sync_service import sync_integration

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────


def _callback_uri(provider: str) -> str:
    return f"{settings.OAUTH_REDIRECT_BASE_URL}/api/v1/integrations/oauth/{provider}/callback"


def _create_oauth_state(user_id: uuid.UUID, provider: str) -> str:
    payload = {
        "sub": str(user_id),
        "provider": provider,
        "type": "oauth_state",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _decode_oauth_state(state: str) -> dict:
    return jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])


async def _get_integration(
    integration_id: uuid.UUID, user: User, db: AsyncSession
) -> IntegrationConfig:
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_id,
            IntegrationConfig.user_id == user.id,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Integration not found")
    return cfg


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationConfig)
        .where(IntegrationConfig.user_id == current_user.id)
        .order_by(IntegrationConfig.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: IntegrationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect an integration using an internal API token (non-OAuth path)."""
    if body.api_token is None:
        raise HTTPException(
            status_code=400,
            detail="api_token required for non-OAuth integration setup. "
            "For OAuth providers use GET /integrations/oauth/{provider}/url",
        )

    # Validate provider exists
    try:
        provider_cls = get_provider_class(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Instantiate a temporary provider to detect provider_type
    from app.integrations.base import ProviderContext

    dummy_ctx = ProviderContext(
        access_token=body.api_token,
        refresh_token=None,
        token_expires_at=None,
        extra_config=body.config or {},
    )
    provider = provider_cls(dummy_ctx)

    cfg = IntegrationConfig(
        user_id=current_user.id,
        provider=body.provider,
        provider_type=provider.provider_type,
        display_name=body.display_name or body.provider.replace("_", " ").title(),
        # Store the token as the access token (encrypted)
        access_token_encrypted=encrypt_token(body.api_token),
        config={**(body.config or {}), "auth_type": "token"},
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_integration(integration_id, current_user, db)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: uuid.UUID,
    body: IntegrationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_integration(integration_id, current_user, db)

    if body.is_enabled is not None:
        cfg.is_enabled = body.is_enabled
    if body.display_name is not None:
        cfg.display_name = body.display_name
    if body.config is not None:
        cfg.config = {**(cfg.config or {}), **body.config}

    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_integration(integration_id, current_user, db)
    await db.delete(cfg)
    await db.commit()


# ── Sync ─────────────────────────────────────────────────────────────────────


@router.post("/{integration_id}/sync", response_model=SyncResult)
async def trigger_sync(
    integration_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_integration(integration_id, current_user, db)
    if not cfg.is_enabled:
        raise HTTPException(status_code=400, detail="Integration is disabled")
    return await sync_integration(cfg, db)


# ── CalDAV (Basic Auth connect) ───────────────────────────────────────────────


@router.post(
    "/caldav/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_caldav(
    body: CalDAVConnectBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect Apple CalDAV using an app-specific password (Basic Auth).

    Credentials are encrypted with Fernet and stored in credentials_encrypted.
    The raw password is never stored in plaintext.
    """
    import json

    from app.core.encryption import encrypt_token

    creds_json = json.dumps(
        {
            "username": body.username,
            "password": body.password,
            "caldav_url": body.caldav_url,
        }
    )

    # Upsert — replace existing Apple CalDAV config for this user if present
    existing = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.provider == "apple_caldav",
        )
    )
    cfg = existing.scalar_one_or_none()

    if cfg:
        cfg.credentials_encrypted = encrypt_token(creds_json)
        cfg.config = {"caldav_url": body.caldav_url, "auth_type": "basic"}
        cfg.is_enabled = True
        if body.display_name:
            cfg.display_name = body.display_name
    else:
        cfg = IntegrationConfig(
            user_id=current_user.id,
            provider="apple_caldav",
            provider_type="calendar",
            display_name=body.display_name or "Apple Calendar",
            credentials_encrypted=encrypt_token(creds_json),
            config={"caldav_url": body.caldav_url, "auth_type": "basic"},
        )
        db.add(cfg)

    await db.commit()
    await db.refresh(cfg)
    return cfg


# ── OAuth ─────────────────────────────────────────────────────────────────────


@router.get("/oauth/{provider}/url", response_model=OAuthUrlResponse)
async def get_oauth_url(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    try:
        provider_cls = get_provider_class(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    state = _create_oauth_state(current_user.id, provider)
    redirect_uri = _callback_uri(provider)
    url = provider_cls.get_oauth_url(state, redirect_uri)
    return OAuthUrlResponse(url=url, state=state)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handles the OAuth redirect from the external provider.

    Validates the state JWT, exchanges the code for tokens, stores them encrypted,
    then redirects to the mobile deep link.
    """
    # ── Validate state ───────────────────────────────────────────────────────
    try:
        state_payload = _decode_oauth_state(state)
        if state_payload.get("type") != "oauth_state":
            raise ValueError("invalid state type")
        if state_payload.get("provider") != provider:
            raise ValueError("provider mismatch")
        user_id = uuid.UUID(state_payload["sub"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    # ── Load user ────────────────────────────────────────────────────────────
    from app.models.user import User as UserModel

    user_result = await db.execute(
        select(UserModel).where(UserModel.id == user_id, UserModel.is_active == True)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    # ── Exchange code ────────────────────────────────────────────────────────
    try:
        provider_cls = get_provider_class(provider)
        redirect_uri = _callback_uri(provider)
        token_data = await provider_cls.exchange_code(code, redirect_uri)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    # ── Instantiate provider to get provider_type ────────────────────────────
    from app.integrations.base import ProviderContext

    ctx = ProviderContext(
        access_token=token_data.access_token,
        refresh_token=token_data.refresh_token,
        token_expires_at=token_data.expires_at,
        extra_config=token_data.extra,
    )
    provider_instance = provider_cls(ctx)

    # ── Upsert IntegrationConfig ─────────────────────────────────────────────
    existing_result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.provider == provider,
        )
    )
    cfg = existing_result.scalar_one_or_none()

    if cfg:
        cfg.access_token_encrypted = encrypt_token(token_data.access_token)
        if token_data.refresh_token:
            cfg.refresh_token_encrypted = encrypt_token(token_data.refresh_token)
        cfg.token_expires_at = token_data.expires_at
        cfg.oauth_scope = token_data.scope
        cfg.is_enabled = True
        cfg.config = {**(cfg.config or {}), **token_data.extra, "auth_type": "oauth"}
    else:
        cfg = IntegrationConfig(
            user_id=user_id,
            provider=provider,
            provider_type=provider_instance.provider_type,
            display_name=provider.replace("_", " ").title(),
            access_token_encrypted=encrypt_token(token_data.access_token),
            refresh_token_encrypted=(
                encrypt_token(token_data.refresh_token) if token_data.refresh_token else None
            ),
            token_expires_at=token_data.expires_at,
            oauth_scope=token_data.scope,
            config={**token_data.extra, "auth_type": "oauth"},
        )
        db.add(cfg)

    await db.commit()

    # ── Redirect to mobile deep link ─────────────────────────────────────────
    deep_link = f"{settings.MOBILE_DEEP_LINK_SCHEME}://oauth/callback?success=true&provider={provider}"
    return RedirectResponse(url=deep_link, status_code=302)
