from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

from tradenest.config import Settings
from tradenest.db import migrate, session
from tradenest.services.paper_orders import evaluate_open_orders_for_symbol


def parse_ticker_last_price(data: Dict[str, Any]) -> Optional[float]:
    if data.get("retCode") != 0:
        return None
    ticker_list = data.get("result", {}).get("list", [])
    if not ticker_list:
        return None
    last_price = ticker_list[0].get("lastPrice")
    if last_price is None:
        return None
    return float(last_price)


def parse_instrument_metadata(data: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if data.get("retCode") != 0:
        return None, None
    instruments = data.get("result", {}).get("list", [])
    if not instruments:
        return None, None

    instrument = instruments[0]
    lot_size = instrument.get("lotSizeFilter", {})
    price_filter = instrument.get("priceFilter", {})
    return lot_size.get("qtyStep"), price_filter.get("tickSize")


def _get_json(url: str, timeout: int) -> Dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_ticker_last_price(symbol: str, settings: Settings) -> Optional[float]:
    query = urlencode({"category": settings.price_feed_category, "symbol": symbol})
    url = f"{settings.price_feed_base_url}/v5/market/tickers?{query}"
    return parse_ticker_last_price(
        _get_json(url, timeout=settings.price_feed_request_timeout_seconds)
    )


def fetch_instrument_metadata(
    symbol: str,
    settings: Settings,
) -> tuple[Optional[str], Optional[str]]:
    query = urlencode({"category": settings.price_feed_category, "symbol": symbol})
    url = f"{settings.price_feed_base_url}/v5/market/instruments-info?{query}"
    return parse_instrument_metadata(
        _get_json(url, timeout=settings.price_feed_request_timeout_seconds)
    )


def cache_instrument_metadata(
    db: sqlite3.Connection,
    *,
    symbol: str,
    qty_step: Optional[str],
    tick_size: Optional[str],
) -> None:
    db.execute(
        """
        INSERT INTO instrument_metadata (symbol, qty_step, tick_size, updated_at_utc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            qty_step = excluded.qty_step,
            tick_size = excluded.tick_size,
            updated_at_utc = excluded.updated_at_utc
        """,
        (symbol, qty_step, tick_size, datetime.now(timezone.utc).isoformat()),
    )


def refresh_instrument_metadata(
    db: sqlite3.Connection,
    *,
    symbol: str,
    settings: Settings,
) -> None:
    try:
        qty_step, tick_size = fetch_instrument_metadata(symbol, settings)
    except Exception:
        return
    if qty_step is not None or tick_size is not None:
        cache_instrument_metadata(
            db,
            symbol=symbol,
            qty_step=qty_step,
            tick_size=tick_size,
        )


def open_paper_symbols(db: sqlite3.Connection) -> list[str]:
    rows = db.execute(
        "SELECT DISTINCT symbol FROM paper_orders WHERE status = 'open'"
    ).fetchall()
    return [row["symbol"] for row in rows]


def poll_open_paper_orders_once(settings: Settings) -> None:
    if not settings.price_feed_enabled:
        return
    with session(settings.db_path) as db:
        migrate(db)
        for symbol in settings.allowed_symbols:
            refresh_instrument_metadata(db, symbol=symbol, settings=settings)
        for symbol in open_paper_symbols(db):
            try:
                latest_price = fetch_ticker_last_price(symbol, settings)
            except Exception:
                continue
            if latest_price is None:
                continue
            evaluate_open_orders_for_symbol(
                db,
                symbol=symbol,
                latest_price=latest_price,
                max_holding_bars=settings.max_holding_bars,
            )
