from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import sqlite3
from zoneinfo import ZoneInfo

from tradenest.config import Settings
from tradenest.db import log_audit
from tradenest.schemas import SignalState


def trade_day_for(value: datetime, timezone_name: str) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def _system_state_int(db: sqlite3.Connection, key: str, default: int = 0) -> int:
    row = db.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return int(row["value"])


def _system_state_bool(db: sqlite3.Connection, key: str, default: bool = False) -> bool:
    row = db.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return str(row["value"]).strip().lower() in {"1", "true", "yes", "on"}


def _daily_loss_eur(
    db: sqlite3.Connection,
    *,
    trade_day: str,
    timezone_name: str,
) -> float:
    risk_row = db.execute(
        """
        SELECT COALESCE(SUM(CASE
            WHEN CAST(realized_pnl_eur AS REAL) < 0
            THEN CAST(realized_pnl_eur AS REAL)
            ELSE 0
        END), 0) AS loss
        FROM risk_decisions
        WHERE trade_day = ?
        """,
        (trade_day,),
    ).fetchone()
    paper_loss = 0.0
    order_rows = db.execute(
        """
        SELECT realized_pnl_eur, closed_at_utc
        FROM paper_orders
        WHERE status = 'closed'
          AND realized_pnl_eur IS NOT NULL
          AND closed_at_utc IS NOT NULL
        """
    ).fetchall()
    for row in order_rows:
        closed_at = datetime.fromisoformat(row["closed_at_utc"])
        if trade_day_for(closed_at, timezone_name) == trade_day:
            pnl = float(row["realized_pnl_eur"])
            if pnl < 0:
                paper_loss += pnl

    return abs(float(risk_row["loss"]) + paper_loss)


def _trade_count_today(db: sqlite3.Connection, trade_day: str) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM risk_decisions
        WHERE trade_day = ? AND decision = 'passed'
        """,
        (trade_day,),
    ).fetchone()
    return int(row["count"])


def _normalize_side(side: str) -> str:
    if side in {"buy", "long"}:
        return "buy"
    return "sell"


def _open_positions(
    db: sqlite3.Connection,
    *,
    state: SignalState,
    settings: Settings,
) -> int:
    rows = db.execute("SELECT side, strategy, symbol FROM paper_orders WHERE status = 'open'").fetchall()
    count = 0
    incoming_side = _normalize_side(state.payload.side)
    for row in rows:
        is_counter_order = (
            settings.close_on_counter_signal
            and row["strategy"] == state.payload.strategy
            and row["symbol"] == state.payload.symbol
            and _normalize_side(row["side"]) != incoming_side
        )
        if not is_counter_order:
            count += 1
    return max(_system_state_int(db, "open_positions", 0), count)


def _cooldown_active(
    db: sqlite3.Connection,
    *,
    state: SignalState,
    cooldown_minutes: int,
) -> bool:
    cutoff = state.received_at.astimezone(timezone.utc) - timedelta(
        minutes=cooldown_minutes
    )
    row = db.execute(
        """
        SELECT id
        FROM risk_decisions
        WHERE decision = 'passed'
          AND strategy = ?
          AND symbol = ?
          AND created_at_utc >= ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            state.payload.strategy,
            state.payload.symbol,
            cutoff.isoformat(),
        ),
    ).fetchone()
    return row is not None


class RiskGateStage:
    def __call__(
        self,
        state: SignalState,
        db: sqlite3.Connection,
        settings: Settings,
    ) -> SignalState:
        trade_day = trade_day_for(state.received_at, settings.timezone)
        daily_loss = _daily_loss_eur(
            db,
            trade_day=trade_day,
            timezone_name=settings.timezone,
        )
        trade_count = _trade_count_today(db, trade_day)
        open_positions = _open_positions(db, state=state, settings=settings)
        kill_switch = settings.kill_switch or _system_state_bool(db, "kill_switch", False)

        reason_codes = []
        if settings.mode != "paper":
            reason_codes.append("mode_not_paper")
        if kill_switch:
            reason_codes.append("kill_switch_enabled")
        if state.payload.strategy != settings.strategy:
            reason_codes.append("strategy_not_allowed")
        if state.payload.symbol not in settings.allowed_symbols:
            reason_codes.append("symbol_not_allowed")
        if trade_count >= settings.max_trades_per_day:
            reason_codes.append("max_trades_per_day_reached")
        if open_positions >= settings.max_open_positions:
            reason_codes.append("max_open_positions_reached")
        if _cooldown_active(
            db,
            state=state,
            cooldown_minutes=settings.cooldown_minutes,
        ):
            reason_codes.append("cooldown_active")
        if state.atr is None:
            reason_codes.append("atr_missing")
        elif not math.isfinite(state.atr) or state.atr <= 0:
            reason_codes.append("atr_invalid")
        if daily_loss >= settings.daily_loss_cap_eur:
            reason_codes.append("daily_loss_cap_reached")
        if not state.signal_valid:
            reason_codes.append("signal_engine_rejected")

        decision = "blocked" if reason_codes else "passed"
        created_at_utc = state.received_at.astimezone(timezone.utc).isoformat()

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
                state.signal_id,
                state.dedupe_key,
                decision,
                settings.mode,
                state.payload.symbol,
                state.payload.strategy,
                str(state.atr) if state.atr is not None else None,
                int(state.signal_valid),
                state.signal_grade,
                state.rubric_version,
                json.dumps(reason_codes, sort_keys=True),
                str(daily_loss),
                "0",
                trade_count,
                open_positions,
                trade_day,
                created_at_utc,
            ),
        )

        if decision == "blocked":
            log_audit(
                db,
                event_type="risk_gate",
                status_value="blocked",
                reason=",".join(reason_codes),
                path_token_valid=True,
                payload_token_valid=True,
                source=state.payload.source.value,
                dedupe_key=state.dedupe_key,
            )

        state.risk_decision = decision
        state.risk_reason_codes = reason_codes
        return state
