from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from tradenest.db import migrate, session
from tradenest.services.paper_orders import close_order
from tradenest.services.telegram_service import (
    TelegramNotifier,
    handle_telegram_update,
    safe_text,
)


class FakeTelegramClient:
    def __init__(self):
        self.messages = []

    def send_message(self, *, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})


def telegram_settings(settings):
    return replace(
        settings,
        telegram_enabled=True,
        telegram_bot_token="telegram-secret-token",
        telegram_allowed_chat_id="12345",
    )


def update(command: str, chat_id: str = "12345"):
    return {"message": {"chat": {"id": chat_id}, "text": command}}


def insert_closed_candidate_order(settings):
    with session(settings.db_path) as db:
        migrate(db)
        signal = db.execute(
            """
            INSERT INTO signals (
                dedupe_key,
                source,
                symbol,
                side,
                strategy,
                timeframe,
                event_time,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"telegram-signal-{datetime.now(timezone.utc).timestamp()}",
                "Manual",
                "BTCUSDT",
                "buy",
                settings.strategy,
                "5m",
                datetime.now(timezone.utc).isoformat(),
                "{}",
            ),
        )
        order = db.execute(
            """
            INSERT INTO paper_orders (
                signal_id,
                dedupe_key,
                status,
                symbol,
                strategy,
                side,
                entry_price,
                quantity_eur,
                quantity,
                atr,
                sl_price,
                tp_price,
                max_holding_bars,
                opened_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.lastrowid,
                f"telegram-order-{datetime.now(timezone.utc).timestamp()}",
                "open",
                "BTCUSDT",
                settings.strategy,
                "buy",
                "100",
                "100",
                "1",
                "10",
                "90",
                "120",
                settings.max_holding_bars,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return order.lastrowid


def test_kill_sets_kill_switch_true(settings):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()

    handled = handle_telegram_update(update("/kill"), settings, client=fake)

    assert handled is True
    with session(settings.db_path) as db:
        row = db.execute("SELECT value FROM system_state WHERE key = 'kill_switch'").fetchone()
        audit = db.execute("SELECT reason FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["value"] == "true"
    assert audit["reason"] == "kill"
    assert "enabled" in fake.messages[0]["text"]


def test_kill_command_blocks_new_signals(client, settings, payload):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()

    handle_telegram_update(update("/kill"), settings, client=fake)
    response = client.post(
        f"/webhook/tradingview/{settings.tradingview_path_token}",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    assert "kill_switch_enabled" in response.json()["risk_reason_codes"]


def test_unkill_sets_kill_switch_false(settings):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()
    handle_telegram_update(update("/kill"), settings, client=fake)

    handled = handle_telegram_update(update("/unkill"), settings, client=fake)

    assert handled is True
    with session(settings.db_path) as db:
        row = db.execute("SELECT value FROM system_state WHERE key = 'kill_switch'").fetchone()
        audit = db.execute("SELECT reason FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["value"] == "false"
    assert audit["reason"] == "unkill"
    assert "disabled" in fake.messages[-1]["text"]


def test_status_returns_expected_fields(client, settings, payload):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()
    client.post(f"/webhook/tradingview/{settings.tradingview_path_token}", json=payload)

    handled = handle_telegram_update(update("/status"), settings, client=fake)

    assert handled is True
    text = fake.messages[0]["text"]
    for field in (
        "project=TradeNest",
        "mode=paper",
        "kill_switch=False",
        "today_signals=",
        "today_blocked_signals=",
        "open_paper_positions=",
        "today_paper_pnl_eur=",
        "latest_run_status=",
    ):
        assert field in text


def test_unauthorized_chat_id_is_ignored(settings):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()

    handled = handle_telegram_update(update("/kill", chat_id="999"), settings, client=fake)

    assert handled is False
    assert fake.messages == []
    with session(settings.db_path) as db:
        migrate(db)
        row = db.execute("SELECT value FROM system_state WHERE key = 'kill_switch'").fetchone()
    assert row is None


def test_blocked_signal_notification_is_formatted_without_secrets(settings):
    settings = replace(
        telegram_settings(settings),
        tradingview_path_token="path-secret",
        tradingview_auth_token="payload-secret",
    )
    fake = FakeTelegramClient()
    notifier = TelegramNotifier(settings, client=fake)

    notifier.signal_blocked(
        symbol="BTCUSDT",
        side="buy",
        reason_codes=["kill_switch_enabled", "auth_token", "payload-secret"],
    )

    text = fake.messages[0]["text"]
    assert "signal blocked" in text
    assert "path-secret" not in text
    assert "payload-secret" not in text
    assert "auth_token" not in text


def test_paper_order_opened_notification_is_formatted_correctly(client, settings, payload):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()
    notifier = TelegramNotifier(settings, client=fake)
    client.post(f"/webhook/tradingview/{settings.tradingview_path_token}", json=payload)

    with session(settings.db_path) as db:
        order = db.execute("SELECT * FROM paper_orders ORDER BY id DESC LIMIT 1").fetchone()

    notifier.paper_order_opened(order)

    text = fake.messages[0]["text"]
    assert "paper order opened" in text
    assert "symbol=BTCUSDT" in text
    assert "sl=" in text
    assert "tp=" in text


def test_paper_order_closed_notification_includes_exit_reason_and_pnl(settings):
    settings = telegram_settings(settings)
    fake = FakeTelegramClient()
    order_id = insert_closed_candidate_order(settings)

    with session(settings.db_path) as db:
        order = db.execute("SELECT * FROM paper_orders WHERE id = ?", (order_id,)).fetchone()
        close_order(
            db,
            order=order,
            exit_price=120,
            exit_reason="take_profit_hit",
            notifier=TelegramNotifier(settings, client=fake),
        )

    text = fake.messages[0]["text"]
    assert "paper order closed" in text
    assert "exit_reason=take_profit_hit" in text
    assert "pnl_eur=" in text
    assert "pnl_percent=" in text


def test_telegram_disabled_mode_does_not_send_messages(settings):
    fake = FakeTelegramClient()
    notifier = TelegramNotifier(settings, client=fake)

    sent = notifier.signal_accepted(signal_id=1, symbol="BTCUSDT", side="buy")
    handled = handle_telegram_update(update("/status"), settings, client=fake)

    assert sent is False
    assert handled is False
    assert fake.messages == []


def test_safe_formatting_masks_known_secrets(settings):
    settings = telegram_settings(settings)
    text = safe_text(
        "auth_token path-secret payload-secret telegram-secret-token",
        settings,
    )

    assert "auth_token" not in text
    assert "path-secret" not in text
    assert "payload-secret" not in text
    assert "telegram-secret-token" not in text
