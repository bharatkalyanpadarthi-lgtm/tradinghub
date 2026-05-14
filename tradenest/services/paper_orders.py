from __future__ import annotations

from datetime import datetime, timezone
import sqlite3


def calculate_pnl(order: sqlite3.Row, exit_price: float) -> tuple[float, float]:
    entry_price = float(order["entry_price"])
    quantity = float(order["quantity"])
    if order["side"] == "buy":
        pnl_eur = (exit_price - entry_price) * quantity
        pnl_percent = ((exit_price - entry_price) / entry_price) * 100
    else:
        pnl_eur = (entry_price - exit_price) * quantity
        pnl_percent = ((entry_price - exit_price) / entry_price) * 100
    return pnl_eur, pnl_percent


def close_order(
    db: sqlite3.Connection,
    *,
    order: sqlite3.Row,
    exit_price: float,
    exit_reason: str,
) -> None:
    pnl_eur, pnl_percent = calculate_pnl(order, exit_price)
    db.execute(
        """
        UPDATE paper_orders
        SET status = 'closed',
            exit_price = ?,
            exit_reason = ?,
            realized_pnl_eur = ?,
            realized_pnl_percent = ?,
            closed_at_utc = ?
        WHERE id = ? AND status = 'open'
        """,
        (
            str(exit_price),
            exit_reason,
            str(pnl_eur),
            str(pnl_percent),
            datetime.now(timezone.utc).isoformat(),
            order["id"],
        ),
    )


def evaluate_order_exit(
    db: sqlite3.Connection,
    *,
    order: sqlite3.Row,
    latest_price: float,
    max_holding_bars: int,
) -> str | None:
    side = order["side"]
    sl_price = float(order["sl_price"])
    tp_price = float(order["tp_price"])

    if side == "buy" and latest_price <= sl_price:
        return "stop_loss_hit"
    if side == "buy" and latest_price >= tp_price:
        return "take_profit_hit"
    if side == "sell" and latest_price >= sl_price:
        return "stop_loss_hit"
    if side == "sell" and latest_price <= tp_price:
        return "take_profit_hit"

    bars_held = int(order["bars_held"]) + 1
    db.execute(
        "UPDATE paper_orders SET bars_held = ? WHERE id = ?",
        (bars_held, order["id"]),
    )
    if bars_held >= max_holding_bars:
        return "time_exit"
    return None


def evaluate_open_orders_for_symbol(
    db: sqlite3.Connection,
    *,
    symbol: str,
    latest_price: float,
    max_holding_bars: int,
) -> None:
    rows = db.execute(
        """
        SELECT *
        FROM paper_orders
        WHERE status = 'open' AND symbol = ?
        ORDER BY id
        """,
        (symbol,),
    ).fetchall()
    for row in rows:
        exit_reason = evaluate_order_exit(
            db,
            order=row,
            latest_price=latest_price,
            max_holding_bars=max_holding_bars,
        )
        if exit_reason:
            close_order(
                db,
                order=row,
                exit_price=latest_price,
                exit_reason=exit_reason,
            )
