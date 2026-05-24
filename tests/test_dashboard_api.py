from __future__ import annotations

from tradenest.db import session


def post_signal(client, settings, payload):
    return client.post(
        f"/webhook/tradingview/{settings.tradingview_path_token}",
        json=payload,
    )


def test_api_routes_require_admin_token(client):
    response = client.get(
        "/api/status",
        headers={"X-TradeNest-Admin-Token": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "invalid_admin_token"


def test_generated_api_docs_are_not_public(client):
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


def test_api_status_returns_dashboard_fields(client, settings, payload):
    post_signal(client, settings, payload)

    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    for field in (
        "project",
        "mode",
        "kill_switch",
        "backend_health",
        "today_signals",
        "today_blocked_signals",
        "open_paper_positions",
        "today_paper_pnl_eur",
        "latest_run_status",
    ):
        assert field in data
    assert data["project"] == "TradeNest"
    assert data["backend_health"] == "ok"


def test_api_system_kill_sets_kill_switch_true(client, settings):
    response = client.post("/api/system/kill")

    assert response.status_code == 200
    assert response.json()["kill_switch"] is True
    with session(settings.db_path) as db:
        row = db.execute("SELECT value FROM system_state WHERE key = 'kill_switch'").fetchone()
        audit = db.execute("SELECT reason FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["value"] == "true"
    assert audit["reason"] == "kill"


def test_api_system_unkill_sets_kill_switch_false(client, settings):
    client.post("/api/system/kill")

    response = client.post("/api/system/unkill")

    assert response.status_code == 200
    assert response.json()["kill_switch"] is False
    with session(settings.db_path) as db:
        row = db.execute("SELECT value FROM system_state WHERE key = 'kill_switch'").fetchone()
        audit = db.execute("SELECT reason FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["value"] == "false"
    assert audit["reason"] == "unkill"


def test_api_journal_redacts_secrets(client, settings, payload):
    payload["metadata"] = {
        "atr_fixture": 125.5,
        "auth_token": settings.tradingview_auth_token,
        "secret_path_token": settings.tradingview_path_token,
    }
    post_signal(client, settings, payload)

    response = client.get("/api/journal")

    assert response.status_code == 200
    rendered = response.text
    assert settings.tradingview_auth_token not in rendered
    assert settings.tradingview_path_token not in rendered
    assert "auth_token" not in rendered
    assert "secret_path_token" not in rendered


def test_api_risk_status_returns_dashboard_fields(client, settings, payload):
    post_signal(client, settings, payload)

    response = client.get("/api/risk/status")

    assert response.status_code == 200
    data = response.json()
    assert data["daily_loss_cap_eur"] == settings.daily_loss_cap_eur
    assert data["max_open_positions"] == settings.max_open_positions
    assert data["allowed_symbols"] == list(settings.allowed_symbols)
    assert data["allowed_strategies"] == [settings.strategy]


def test_telegram_webhook_requires_secret_header(client):
    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "invalid_telegram_webhook_secret"


def test_telegram_webhook_accepts_configured_secret(client, settings):
    response = client.post(
        "/telegram/webhook",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret_token
        },
        json={},
    )

    assert response.status_code == 200
    assert response.json() == {"handled": False}


def test_telegram_webhook_rejects_invalid_json(client, settings):
    response = client.post(
        "/telegram/webhook",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret_token,
            "Content-Type": "application/json",
        },
        content="{",
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "invalid_json_body"
