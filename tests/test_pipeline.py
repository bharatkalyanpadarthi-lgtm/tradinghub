from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from tradenest.db import session
from tradenest.stages.risk_gate import trade_day_for


def latest_risk_decision(settings):
    with session(settings.db_path) as db:
        return db.execute(
            "SELECT * FROM risk_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()


def reason_codes(row):
    return json.loads(row["reason_codes_json"])


def post_signal(client, settings, payload, path_token=None):
    token = path_token if path_token is not None else settings.tradingview_path_token
    return client.post(f"/webhook/tradingview/{token}", json=payload)


def insert_passed_risk_decision(settings, *, trade_day=None, realized_pnl_eur=0):
    trade_day = trade_day or trade_day_for(datetime.now(timezone.utc), settings.timezone)
    created_at_utc = datetime.now(timezone.utc) - timedelta(hours=1)
    seed_id = uuid4().hex
    with session(settings.db_path) as db:
        cursor = db.execute(
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
                f"seed-signal-{seed_id}",
                "Manual",
                "BTCUSDT",
                "buy",
                settings.strategy,
                "5m",
                datetime.now(timezone.utc).isoformat(),
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO risk_decisions (
                signal_id,
                dedupe_key,
                decision,
                mode,
                symbol,
                strategy,
                atr,
                signal_valid,
                signal_grade,
                rubric_version,
                reason_codes_json,
                daily_loss_eur,
                realized_pnl_eur,
                trade_count_today,
                open_positions,
                trade_day,
                created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                f"seed-risk-{seed_id}",
                "passed",
                "paper",
                "BTCUSDT",
                settings.strategy,
                "100",
                1,
                "pass",
                settings.strategy,
                "[]",
                "0",
                str(realized_pnl_eur),
                0,
                0,
                trade_day,
                created_at_utc.isoformat(),
            ),
        )


def test_allowed_btcusdt_signal_passes_risk_when_atr_is_available(
    client, settings, payload
):
    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "passed"
    row = latest_risk_decision(settings)
    assert row["decision"] == "passed"
    assert row["symbol"] == "BTCUSDT"
    assert float(row["atr"]) == 125.5


def test_unknown_symbol_is_blocked(client, settings, payload):
    payload["symbol"] = "SOLUSDT"

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "symbol_not_allowed" in reason_codes(row)
    with session(settings.db_path) as db:
        audit_row = db.execute(
            """
            SELECT event_type, status, reason
            FROM audit_logs
            WHERE event_type = 'risk_gate'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    assert audit_row["event_type"] == "risk_gate"
    assert audit_row["status"] == "blocked"
    assert "symbol_not_allowed" in audit_row["reason"]


def test_unknown_strategy_is_blocked(client, settings, payload):
    payload["strategy"] = "other_strategy"

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    codes = reason_codes(row)
    assert "strategy_not_allowed" in codes
    assert "signal_engine_rejected" in codes


def test_kill_switch_blocks_signal(client, settings, payload):
    with session(settings.db_path) as db:
        db.execute(
            "INSERT INTO system_state (key, value) VALUES (?, ?)",
            ("kill_switch", "true"),
        )

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "kill_switch_enabled" in reason_codes(row)


def test_missing_atr_blocks_signal(client, settings, payload):
    payload["metadata"] = {}

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "atr_missing" in reason_codes(row)


def test_candle_data_calculates_atr_without_fixture(client, settings, payload):
    payload["metadata"] = {}
    payload["candles"] = [
        {"high": 110 + index, "low": 100 + index, "close": 105 + index}
        for index in range(settings.atr_period)
    ]

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "passed"
    row = latest_risk_decision(settings)
    assert float(row["atr"]) == 10


def test_max_open_positions_blocks_signal(client, settings, payload):
    with session(settings.db_path) as db:
        db.execute(
            "INSERT INTO system_state (key, value) VALUES (?, ?)",
            ("open_positions", str(settings.max_open_positions)),
        )

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "max_open_positions_reached" in reason_codes(row)


def test_cooldown_blocks_repeated_accepted_signal_for_same_strategy_and_symbol(
    client, settings, payload
):
    first = post_signal(client, settings, payload)
    payload["alert_id"] = "tv-alert-2"
    second = post_signal(client, settings, payload)

    assert first.status_code == 200
    assert first.json()["risk_decision"] == "passed"
    assert second.status_code == 200
    assert second.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "cooldown_active" in reason_codes(row)


def test_max_trades_per_day_blocks_after_limit(client, settings, payload):
    for _ in range(settings.max_trades_per_day):
        insert_passed_risk_decision(settings)

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "max_trades_per_day_reached" in reason_codes(row)


def test_daily_loss_cap_blocks_when_persisted_daily_loss_reaches_cap(
    client, settings, payload
):
    insert_passed_risk_decision(settings, realized_pnl_eur=-settings.daily_loss_cap_eur)

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["risk_decision"] == "blocked"
    row = latest_risk_decision(settings)
    assert "daily_loss_cap_reached" in reason_codes(row)


def test_amsterdam_daily_boundary_is_used_for_today_calculations():
    just_before_midnight = datetime(2026, 5, 13, 21, 59, tzinfo=timezone.utc)
    at_midnight = datetime(2026, 5, 13, 22, 0, tzinfo=timezone.utc)

    assert trade_day_for(just_before_midnight, "Europe/Amsterdam") == "2026-05-13"
    assert trade_day_for(at_midnight, "Europe/Amsterdam") == "2026-05-14"
