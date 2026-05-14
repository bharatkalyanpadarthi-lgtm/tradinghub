from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, Optional, Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from zoneinfo import ZoneInfo

from tradenest.config import Settings
from tradenest.db import log_audit, migrate, session


class TelegramClient(Protocol):
    def send_message(self, *, chat_id: str, text: str) -> None:
        ...


class HttpTelegramClient:
    def __init__(self, bot_token: str):
        self._bot_token = bot_token

    def send_message(self, *, chat_id: str, text: str) -> None:
        body = urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        with urlopen(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            data=body,
            timeout=5,
        ):
            return


def telegram_enabled(settings: Settings) -> bool:
    return bool(
        settings.telegram_enabled
        and settings.telegram_bot_token
        and settings.telegram_allowed_chat_id
    )


def default_telegram_client(settings: Settings) -> TelegramClient:
    return HttpTelegramClient(settings.telegram_bot_token)


def safe_text(text: str, settings: Settings) -> str:
    redacted = text
    secrets = (
        settings.tradingview_path_token,
        settings.tradingview_auth_token,
        settings.telegram_bot_token,
    )
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    for marker in ("auth_token", "secret_path_token", "TELEGRAM_BOT_TOKEN"):
        redacted = redacted.replace(marker, "[redacted]")
    return redacted


class TelegramNotifier:
    def __init__(
        self,
        settings: Settings,
        client: Optional[TelegramClient] = None,
    ):
        self._settings = settings
        self._client = client or default_telegram_client(settings)

    @property
    def enabled(self) -> bool:
        return telegram_enabled(self._settings)

    def send(self, text: str, *, chat_id: Optional[str] = None) -> bool:
        if not self.enabled:
            return False
        target_chat_id = chat_id or self._settings.telegram_allowed_chat_id
        if target_chat_id != self._settings.telegram_allowed_chat_id:
            return False
        try:
            self._client.send_message(
                chat_id=target_chat_id,
                text=safe_text(text, self._settings),
            )
        except Exception:
            return False
        return True

    def signal_accepted(self, *, signal_id: int, symbol: str, side: str) -> bool:
        return self.send(
            f"TradeNest signal accepted\nsignal_id={signal_id}\nsymbol={symbol}\nside={side}"
        )

    def signal_blocked(self, *, symbol: str, side: str, reason_codes: list[str]) -> bool:
        reasons = ", ".join(reason_codes) if reason_codes else "unknown"
        return self.send(
            f"TradeNest signal blocked\nsymbol={symbol}\nside={side}\nreasons={reasons}"
        )

    def paper_order_opened(self, order: sqlite3.Row) -> bool:
        return self.send(
            "\n".join(
                (
                    "TradeNest paper order opened",
                    f"order_id={order['id']}",
                    f"symbol={order['symbol']}",
                    f"side={order['side']}",
                    f"entry={order['entry_price']}",
                    f"sl={order['sl_price']}",
                    f"tp={order['tp_price']}",
                )
            )
        )

    def paper_order_closed(self, order: sqlite3.Row) -> bool:
        return self.send(
            "\n".join(
                (
                    "TradeNest paper order closed",
                    f"order_id={order['id']}",
                    f"symbol={order['symbol']}",
                    f"exit_reason={order['exit_reason']}",
                    f"exit_price={order['exit_price']}",
                    f"pnl_eur={order['realized_pnl_eur']}",
                    f"pnl_percent={order['realized_pnl_percent']}",
                )
            )
        )

    def system_error(self, reason: str) -> bool:
        return self.send(f"TradeNest system error\nreason={reason}")


def system_state_bool(db: sqlite3.Connection, key: str, default: bool = False) -> bool:
    row = db.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return str(row["value"]).strip().lower() in {"1", "true", "yes", "on"}


def set_system_state(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute(
        """
        INSERT INTO system_state (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def trade_day(settings: Settings, value: Optional[datetime] = None) -> str:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(ZoneInfo(settings.timezone)).date().isoformat()


def today_summary(db: sqlite3.Connection, settings: Settings) -> Dict[str, Any]:
    day = trade_day(settings)
    signals = 0
    for row in db.execute("SELECT event_time FROM signals").fetchall():
        if trade_day(settings, datetime.fromisoformat(row["event_time"])) == day:
            signals += 1

    blocked = db.execute(
        "SELECT COUNT(*) FROM risk_decisions WHERE trade_day = ? AND decision = 'blocked'",
        (day,),
    ).fetchone()[0]
    opened = 0
    for row in db.execute("SELECT opened_at_utc FROM paper_orders").fetchall():
        if trade_day(settings, datetime.fromisoformat(row["opened_at_utc"])) == day:
            opened += 1

    closed = 0
    pnl = 0.0
    rows = db.execute(
        """
        SELECT closed_at_utc, realized_pnl_eur
        FROM paper_orders
        WHERE status = 'closed' AND closed_at_utc IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        if trade_day(settings, datetime.fromisoformat(row["closed_at_utc"])) == day:
            closed += 1
            pnl += float(row["realized_pnl_eur"] or 0)
    return {
        "trade_day": day,
        "signals": signals,
        "blocked_signals": blocked,
        "paper_orders_opened": opened,
        "paper_orders_closed": closed,
        "paper_pnl_eur": float(pnl),
    }


def status_summary(db: sqlite3.Connection, settings: Settings) -> Dict[str, Any]:
    today = today_summary(db, settings)
    open_positions = db.execute(
        "SELECT COUNT(*) FROM paper_orders WHERE status = 'open'"
    ).fetchone()[0]
    latest_run = db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "project": "TradeNest",
        "mode": settings.mode,
        "kill_switch": system_state_bool(db, "kill_switch", settings.kill_switch),
        "today_signals": today["signals"],
        "today_blocked_signals": today["blocked_signals"],
        "open_paper_positions": open_positions,
        "today_paper_pnl_eur": today["paper_pnl_eur"],
        "latest_run_status": latest_run["status"] if latest_run else "none",
    }


def latest_summary(db: sqlite3.Connection) -> Dict[str, Any]:
    row = db.execute(
        """
        SELECT
            runs.id AS run_id,
            signals.source,
            signals.symbol,
            signals.side,
            runs.status AS final_decision,
            risk_decisions.decision AS risk_result,
            paper_orders.status AS paper_order_status
        FROM runs
        LEFT JOIN signals ON signals.id = runs.signal_id
        LEFT JOIN risk_decisions ON risk_decisions.signal_id = signals.id
        LEFT JOIN paper_orders ON paper_orders.run_id = runs.id
        ORDER BY runs.id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else {}


def format_dict(title: str, data: Dict[str, Any]) -> str:
    lines = [title]
    for key, value in data.items():
        lines.append(f"{key}={value}")
    return "\n".join(lines)


def handle_command_text(command: str, db: sqlite3.Connection, settings: Settings) -> str:
    normalized = command.strip().split()[0].lower()
    if normalized == "/status":
        return format_dict("TradeNest status", status_summary(db, settings))
    if normalized == "/kill":
        set_system_state(db, "kill_switch", "true")
        log_audit(db, event_type="telegram", status_value="accepted", reason="kill")
        return "TradeNest kill switch enabled"
    if normalized == "/unkill":
        set_system_state(db, "kill_switch", "false")
        log_audit(db, event_type="telegram", status_value="accepted", reason="unkill")
        return "TradeNest kill switch disabled"
    if normalized == "/today":
        return format_dict("TradeNest today", today_summary(db, settings))
    if normalized == "/latest":
        return format_dict("TradeNest latest", latest_summary(db))
    return "Unsupported TradeNest command"


def handle_telegram_update(
    update: Dict[str, Any],
    settings: Settings,
    client: Optional[TelegramClient] = None,
) -> bool:
    if not telegram_enabled(settings):
        return False
    message = update.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != settings.telegram_allowed_chat_id:
        return False
    text = message.get("text", "")
    if not text.startswith("/"):
        return False

    with session(settings.db_path) as db:
        migrate(db)
        reply = handle_command_text(text, db, settings)
    return TelegramNotifier(settings, client=client).send(reply, chat_id=chat_id)


def handle_telegram_update_json(
    body: bytes,
    settings: Settings,
    client: Optional[TelegramClient] = None,
) -> bool:
    return handle_telegram_update(json.loads(body.decode("utf-8")), settings, client=client)
