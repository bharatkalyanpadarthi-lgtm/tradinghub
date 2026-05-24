from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import math
import sqlite3
from typing import Optional

from tradenest.config import Settings
from tradenest.schemas import SignalState
from tradenest.services.paper_orders import close_order
from tradenest.services.telegram_service import TelegramNotifier


def normalize_side(side: str) -> str:
    if side in {"buy", "long"}:
        return "buy"
    return "sell"


def is_counter_side(existing_side: str, incoming_side: str) -> bool:
    return normalize_side(existing_side) != normalize_side(incoming_side)


def round_quantity(quantity: float, qty_step: Optional[str]) -> str:
    decimal_quantity = Decimal(str(quantity))
    if qty_step:
        step = Decimal(str(qty_step))
        if step > 0:
            rounded = (decimal_quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
            return format(rounded.normalize(), "f")

    return format(decimal_quantity.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN), "f")


def cached_qty_step(db: sqlite3.Connection, state: SignalState) -> Optional[str]:
    row = db.execute(
        "SELECT qty_step FROM instrument_metadata WHERE symbol = ?",
        (state.payload.symbol,),
    ).fetchone()
    if row and row["qty_step"]:
        return row["qty_step"]

    value = state.payload.metadata.get("qtyStep")
    if value is None:
        value = state.payload.metadata.get("qty_step")
    return str(value) if value is not None else None


def close_counter_signal_orders(
    db: sqlite3.Connection,
    *,
    state: SignalState,
    settings: Settings,
) -> None:
    if not settings.close_on_counter_signal:
        return

    incoming_side = normalize_side(state.payload.side)
    rows = db.execute(
        """
        SELECT *
        FROM paper_orders
        WHERE status = 'open' AND strategy = ? AND symbol = ?
        """,
        (state.payload.strategy, state.payload.symbol),
    ).fetchall()
    for row in rows:
        if is_counter_side(row["side"], incoming_side):
            close_order(
                db,
                order=row,
                exit_price=float(state.payload.price),
                exit_reason="counter_signal",
                notifier=TelegramNotifier(settings),
            )


class PaperBrokerStage:
    def __call__(
        self,
        state: SignalState,
        db: sqlite3.Connection,
        settings: Settings,
    ) -> SignalState:
        if state.risk_decision != "passed":
            state.paper_order_status = "skipped"
            return state

        if (
            state.payload.price is None
            or state.payload.price <= 0
            or state.atr is None
            or not math.isfinite(state.atr)
            or state.atr <= 0
        ):
            state.paper_order_status = "skipped"
            return state

        close_counter_signal_orders(db, state=state, settings=settings)

        entry_price = float(state.payload.price)
        atr = float(state.atr)
        side = normalize_side(state.payload.side)
        quantity_eur = settings.default_quantity_eur
        quantity = quantity_eur / entry_price
        quantity_text = round_quantity(quantity, cached_qty_step(db, state))

        if side == "buy":
            sl_price = entry_price - settings.stop_loss_atr_multiplier * atr
            tp_price = entry_price + settings.take_profit_atr_multiplier * atr
        else:
            sl_price = entry_price + settings.stop_loss_atr_multiplier * atr
            tp_price = entry_price - settings.take_profit_atr_multiplier * atr

        cursor = db.execute(
            """
            INSERT INTO paper_orders (
                signal_id,
                run_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.signal_id,
                state.run_id,
                state.dedupe_key,
                "open",
                state.payload.symbol,
                state.payload.strategy,
                side,
                str(entry_price),
                str(quantity_eur),
                quantity_text,
                str(atr),
                str(sl_price),
                str(tp_price),
                settings.max_holding_bars,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        state.paper_order_id = cursor.lastrowid
        state.paper_order_status = "open"
        order = db.execute(
            "SELECT * FROM paper_orders WHERE id = ?",
            (state.paper_order_id,),
        ).fetchone()
        if order is not None:
            TelegramNotifier(settings).paper_order_opened(order)
        return state
