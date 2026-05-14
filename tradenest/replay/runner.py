from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Callable, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


PostResult = tuple[int, Dict[str, Any]]
Poster = Callable[[str, Dict[str, Any]], PostResult]


@dataclass
class ReplaySummary:
    rows_read: int = 0
    posted: int = 0
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: int = 0


def _parse_timestamp(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_side(value: str) -> str:
    upper = value.strip().upper()
    if upper in {"BUY", "LONG"}:
        return "buy"
    if upper in {"SELL", "SHORT"}:
        return "sell"
    return value.strip().lower()


def row_to_payload(row: Dict[str, str], payload_token: str) -> Dict[str, Any]:
    return {
        "auth_token": payload_token,
        "source": "Replay",
        "symbol": row["symbol"].strip(),
        "side": normalize_side(row["side"]),
        "strategy": row["strategy_id"].strip(),
        "timeframe": row["timeframe"].strip(),
        "event_time": _parse_timestamp(row["timestamp"]),
        "alert_id": row["bar_id"].strip(),
        "price": float(row["price"]),
        "metadata": {
            "signal_type": row["signal_type"].strip(),
            "bar_id": row["bar_id"].strip(),
            "atr_fixture": float(row["atr"]),
        },
    }


def read_rows(
    csv_path: str | Path,
    *,
    limit: Optional[int] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
) -> list[Dict[str, str]]:
    selected = []
    with Path(csv_path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if symbol and row["symbol"].strip() != symbol:
                continue
            if strategy and row["strategy_id"].strip() != strategy:
                continue
            selected.append(row)
            if limit is not None and len(selected) >= limit:
                break
    return selected


def default_poster(url: str, payload: Dict[str, Any]) -> PostResult:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except json.JSONDecodeError:
            body = {"detail": str(exc)}
        return exc.code, body
    except URLError as exc:
        return 0, {"error": str(exc.reason)}


def webhook_url(target: str, path_token: str) -> str:
    base = target if target.endswith("/") else f"{target}/"
    return urljoin(base, f"webhook/tradingview/{path_token}")


def _status_from_response(status_code: int, body: Dict[str, Any]) -> str:
    if status_code == 409:
        return "duplicate"
    if 200 <= status_code < 300:
        if body.get("status") == "accepted":
            return "accepted"
        return "posted"
    if status_code == 0:
        return "error"
    return "rejected"


def _sleep_for_speed(previous: Optional[str], current: str, speed: float) -> None:
    if previous is None or speed <= 0:
        return
    previous_time = datetime.fromisoformat(previous)
    current_time = datetime.fromisoformat(current)
    delay = (current_time - previous_time).total_seconds() / speed
    if delay > 0:
        time.sleep(delay)


def run_replay(
    *,
    csv_path: str | Path,
    target: str,
    path_token: str,
    payload_token: str,
    speed: float = 0,
    dry_run: bool = False,
    limit: Optional[int] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    summary_path: Optional[str | Path] = None,
    poster: Poster = default_poster,
    printer: Callable[[str], None] = print,
) -> ReplaySummary:
    rows = read_rows(csv_path, limit=limit, symbol=symbol, strategy=strategy)
    summary = ReplaySummary(rows_read=len(rows))
    url = webhook_url(target, path_token)
    previous_time = None

    for row in rows:
        payload = row_to_payload(row, payload_token)
        if dry_run:
            safe_payload = dict(payload)
            safe_payload["auth_token"] = "[redacted]"
            printer(json.dumps(safe_payload, sort_keys=True))
            previous_time = payload["event_time"]
            continue

        _sleep_for_speed(previous_time, payload["event_time"], speed)
        previous_time = payload["event_time"]
        summary.posted += 1
        status_code, body = poster(url, payload)
        result = _status_from_response(status_code, body)
        if result == "accepted":
            summary.accepted += 1
        elif result == "duplicate":
            summary.duplicates += 1
        elif result == "error":
            summary.errors += 1
        else:
            summary.rejected += 1
        printer(f"{status_code} {result} {payload['alert_id']}")

    summary_json = json.dumps(asdict(summary), indent=2, sort_keys=True)
    printer(summary_json)
    if summary_path:
        Path(summary_path).write_text(f"{summary_json}\n")
    return summary


def payloads_from_rows(rows: Iterable[Dict[str, str]], payload_token: str) -> list[Dict[str, Any]]:
    return [row_to_payload(row, payload_token) for row in rows]
