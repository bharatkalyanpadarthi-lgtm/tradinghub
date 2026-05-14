from __future__ import annotations

from datetime import datetime, timezone
import math

from tradenest.db import migrate, session
from tradenest.services.paper_orders import close_order, evaluate_open_orders_for_symbol
from tradenest.services.price_feed import parse_ticker_last_price


def post_signal(client, settings, payload, path_token=None):
    token = path_token if path_token is not None else settings.tradingview_path_token
    return client.post(f"/webhook/tradingview/{token}", json=payload)


def latest_order(settings):
    with session(settings.db_path) as db:
        return db.execute("SELECT * FROM paper_orders ORDER BY id DESC LIMIT 1").fetchone()


def insert_open_order(
    settings,
    *,
    side="buy",
    entry_price=100,
    quantity=1,
    sl_price=90,
    tp_price=120,
    bars_held=0,
):
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
                f"manual-{datetime.now(timezone.utc).timestamp()}",
                "Manual",
                "BTCUSDT",
                side,
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
                bars_held,
                max_holding_bars,
                opened_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.lastrowid,
                f"manual-order-{datetime.now(timezone.utc).timestamp()}",
                "open",
                "BTCUSDT",
                settings.strategy,
                side,
                str(entry_price),
                str(entry_price * quantity),
                str(quantity),
                "10",
                str(sl_price),
                str(tp_price),
                bars_held,
                settings.max_holding_bars,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return order.lastrowid


def test_paper_order_is_created_after_risk_pass(client, settings, payload):
    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["paper_order_status"] == "open"
    order = latest_order(settings)
    assert order["status"] == "open"
    assert order["symbol"] == "BTCUSDT"


def test_buy_order_has_atr_based_sl_and_tp(client, settings, payload):
    payload["price"] = 100
    payload["metadata"] = {"atr_fixture": 10}

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    order = latest_order(settings)
    assert float(order["sl_price"]) == 85
    assert float(order["tp_price"]) == 125


def test_sell_order_has_atr_based_sl_and_tp(client, settings, payload):
    payload["side"] = "sell"
    payload["price"] = 100
    payload["metadata"] = {"atr_fixture": 10}

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    order = latest_order(settings)
    assert order["side"] == "sell"
    assert float(order["sl_price"]) == 115
    assert float(order["tp_price"]) == 75


def test_paper_quantity_uses_quantity_eur_over_entry_price(client, settings, payload):
    payload["price"] = 100
    payload["metadata"] = {"atr_fixture": 10}

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    order = latest_order(settings)
    assert float(order["quantity_eur"]) == 100
    assert float(order["quantity"]) == 1


def test_quantity_uses_qty_step_rounding_when_available(client, settings, payload):
    with session(settings.db_path) as db:
        db.execute(
            """
            INSERT INTO instrument_metadata (symbol, qty_step, tick_size, updated_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            ("BTCUSDT", "0.001", "0.1", datetime.now(timezone.utc).isoformat()),
        )

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    order = latest_order(settings)
    assert order["quantity"] == "0.001"


def test_fallback_quantity_rounding_uses_eight_decimals(client, settings, payload):
    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    order = latest_order(settings)
    assert order["quantity"] == "0.00153846"


def test_paper_order_can_close_with_stop_loss_hit(settings):
    insert_open_order(settings, side="buy", sl_price=90, tp_price=120)

    with session(settings.db_path) as db:
        evaluate_open_orders_for_symbol(
            db,
            symbol="BTCUSDT",
            latest_price=89,
            max_holding_bars=settings.max_holding_bars,
        )
        order = db.execute("SELECT * FROM paper_orders ORDER BY id DESC LIMIT 1").fetchone()

    assert order["status"] == "closed"
    assert order["exit_reason"] == "stop_loss_hit"


def test_paper_order_can_close_with_take_profit_hit(settings):
    insert_open_order(settings, side="sell", sl_price=110, tp_price=80)

    with session(settings.db_path) as db:
        evaluate_open_orders_for_symbol(
            db,
            symbol="BTCUSDT",
            latest_price=79,
            max_holding_bars=settings.max_holding_bars,
        )
        order = db.execute("SELECT * FROM paper_orders ORDER BY id DESC LIMIT 1").fetchone()

    assert order["status"] == "closed"
    assert order["exit_reason"] == "take_profit_hit"


def test_paper_order_can_close_with_counter_signal(client, settings, payload):
    insert_open_order(settings, side="buy", entry_price=100, quantity=1)
    payload["side"] = "sell"
    payload["price"] = 101

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    with session(settings.db_path) as db:
        closed = db.execute(
            "SELECT * FROM paper_orders WHERE exit_reason = 'counter_signal'"
        ).fetchone()
        open_count = db.execute(
            "SELECT COUNT(*) FROM paper_orders WHERE status = 'open'"
        ).fetchone()[0]

    assert closed["status"] == "closed"
    assert open_count == 1


def test_paper_order_can_close_with_time_exit(settings):
    insert_open_order(settings, bars_held=settings.max_holding_bars - 1)

    with session(settings.db_path) as db:
        evaluate_open_orders_for_symbol(
            db,
            symbol="BTCUSDT",
            latest_price=100,
            max_holding_bars=settings.max_holding_bars,
        )
        order = db.execute("SELECT * FROM paper_orders ORDER BY id DESC LIMIT 1").fetchone()

    assert order["status"] == "closed"
    assert order["exit_reason"] == "time_exit"


def test_pnl_is_calculated_in_eur_and_percent(settings):
    order_id = insert_open_order(settings, entry_price=100, quantity=1)

    with session(settings.db_path) as db:
        order = db.execute("SELECT * FROM paper_orders WHERE id = ?", (order_id,)).fetchone()
        close_order(db, order=order, exit_price=125, exit_reason="manual_close")
        closed = db.execute("SELECT * FROM paper_orders WHERE id = ?", (order_id,)).fetchone()

    assert math.isclose(float(closed["realized_pnl_eur"]), 25)
    assert math.isclose(float(closed["realized_pnl_percent"]), 25)


def test_bybit_ticker_parser_extracts_last_price():
    data = {"retCode": 0, "result": {"list": [{"lastPrice": "65123.45"}]}}

    assert parse_ticker_last_price(data) == 65123.45


def test_bybit_nonzero_retcode_is_handled_safely():
    data = {"retCode": 10001, "retMsg": "bad request"}

    assert parse_ticker_last_price(data) is None


def test_run_and_journal_api(client, settings, payload):
    response = post_signal(client, settings, payload)
    run_id = response.json()["run_id"]

    run_response = client.get(f"/api/runs/{run_id}")
    journal_response = client.get("/api/journal")

    assert run_response.status_code == 200
    assert run_response.json()["run"]["id"] == run_id
    assert len(run_response.json()["stage_events"]) == 4
    assert journal_response.status_code == 200
    assert len(journal_response.json()["paper_orders"]) == 1
