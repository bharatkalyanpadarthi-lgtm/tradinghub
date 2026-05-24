from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


def _matches_configured_token(candidate: Optional[str], configured: str) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate, configured)


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def require_admin_request(
    x_tradenest_admin_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "rejected", "reason": "admin_auth_not_configured"},
        )

    if _matches_configured_token(
        x_tradenest_admin_token,
        settings.admin_token,
    ) or _matches_configured_token(_bearer_token(authorization), settings.admin_token):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"status": "rejected", "reason": "invalid_admin_token"},
    )


def require_telegram_webhook_secret(
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.telegram_webhook_secret_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "rejected",
                "reason": "telegram_webhook_secret_not_configured",
            },
        )

    if _matches_configured_token(
        x_telegram_bot_api_secret_token,
        settings.telegram_webhook_secret_token,
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"status": "rejected", "reason": "invalid_telegram_webhook_secret"},
    )
