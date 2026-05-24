from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import HTTPException

from tradenest.auth import require_admin_request, require_telegram_webhook_secret


pytestmark = pytest.mark.unit


def test_admin_auth_accepts_header_token(settings):
    require_admin_request(
        x_tradenest_admin_token=settings.admin_token,
        authorization=None,
        settings=settings,
    )


def test_admin_auth_accepts_bearer_token(settings):
    require_admin_request(
        x_tradenest_admin_token=None,
        authorization=f"Bearer {settings.admin_token}",
        settings=settings,
    )


def test_admin_auth_rejects_wrong_token(settings):
    with pytest.raises(HTTPException) as exc_info:
        require_admin_request(
            x_tradenest_admin_token="wrong",
            authorization=None,
            settings=settings,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["reason"] == "invalid_admin_token"


def test_admin_auth_fails_closed_when_unconfigured(settings):
    settings = replace(settings, admin_token="")

    with pytest.raises(HTTPException) as exc_info:
        require_admin_request(
            x_tradenest_admin_token="anything",
            authorization=None,
            settings=settings,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["reason"] == "admin_auth_not_configured"


def test_telegram_webhook_secret_accepts_configured_token(settings):
    require_telegram_webhook_secret(
        x_telegram_bot_api_secret_token=settings.telegram_webhook_secret_token,
        settings=settings,
    )


def test_telegram_webhook_secret_rejects_wrong_token(settings):
    with pytest.raises(HTTPException) as exc_info:
        require_telegram_webhook_secret(
            x_telegram_bot_api_secret_token="wrong",
            settings=settings,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["reason"] == "invalid_telegram_webhook_secret"


def test_telegram_webhook_secret_fails_closed_when_unconfigured(settings):
    settings = replace(settings, telegram_webhook_secret_token="")

    with pytest.raises(HTTPException) as exc_info:
        require_telegram_webhook_secret(
            x_telegram_bot_api_secret_token="anything",
            settings=settings,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["reason"] == "telegram_webhook_secret_not_configured"
