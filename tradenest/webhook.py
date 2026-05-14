from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from .config import Settings, get_settings
from .db import log_audit, session
from .pipeline import build_pipeline
from .schemas import SignalSource, SignalState, WebhookPayload


router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_dedupe_key(payload: WebhookPayload) -> str:
    if payload.alert_id:
        identity: Dict[str, Any] = {
            "source": payload.source.value,
            "alert_id": payload.alert_id,
        }
    else:
        identity = {
            "source": payload.source.value,
            "symbol": payload.symbol,
            "side": payload.side,
            "strategy": payload.strategy,
            "timeframe": payload.timeframe,
            "event_time": _as_utc(payload.event_time).isoformat(),
        }

    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@router.post("/webhook/tradingview/{secret_path_token}")
async def receive_tradingview_webhook(
    secret_path_token: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    path_token_valid = bool(settings.tradingview_path_token) and (
        secret_path_token == settings.tradingview_path_token
    )

    body = await request.json()

    with session(settings.db_path) as db:
        if not path_token_valid:
            log_audit(
                db,
                event_type="auth",
                status_value="rejected",
                reason="invalid_path_token",
                path_token_valid=False,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "rejected", "reason": "invalid_path_token"},
            )

        try:
            payload = WebhookPayload.model_validate(body)
        except ValidationError:
            log_audit(
                db,
                event_type="validation",
                status_value="rejected",
                reason="invalid_payload_schema",
                path_token_valid=True,
            )
            raise HTTPException(
                status_code=422,
                detail={"status": "rejected", "reason": "invalid_payload_schema"},
            )

        payload_token_valid = bool(settings.tradingview_auth_token) and (
            payload.auth_token == settings.tradingview_auth_token
        )
        if not payload_token_valid:
            log_audit(
                db,
                event_type="auth",
                status_value="rejected",
                reason="invalid_payload_auth_token",
                path_token_valid=True,
                payload_token_valid=False,
                source=payload.source.value,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "rejected", "reason": "invalid_payload_auth_token"},
            )

        event_time = _as_utc(payload.event_time)
        if payload.source == SignalSource.tradingview:
            age_seconds = (_now() - event_time).total_seconds()
            if age_seconds > settings.tradingview_max_stale_seconds:
                log_audit(
                    db,
                    event_type="stale_check",
                    status_value="rejected",
                    reason="stale_tradingview_signal",
                    path_token_valid=True,
                    payload_token_valid=True,
                    source=payload.source.value,
                )
                raise HTTPException(
                    status_code=422,
                    detail={"status": "rejected", "reason": "stale_tradingview_signal"},
                )

        dedupe_key = build_dedupe_key(payload)
        payload_json = payload.model_dump_json()

        try:
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
                    alert_id,
                    price,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dedupe_key,
                    payload.source.value,
                    payload.symbol,
                    payload.side,
                    payload.strategy,
                    payload.timeframe,
                    event_time.isoformat(),
                    payload.alert_id,
                    str(payload.price) if payload.price is not None else None,
                    payload_json,
                ),
            )
        except sqlite3.IntegrityError:
            log_audit(
                db,
                event_type="dedupe",
                status_value="duplicate",
                reason="duplicate_signal",
                path_token_valid=True,
                payload_token_valid=True,
                source=payload.source.value,
                dedupe_key=dedupe_key,
            )
            db.execute(
                """
                INSERT INTO runs (dedupe_key, status, reason)
                VALUES (?, ?, ?)
                """,
                (dedupe_key, "duplicate", "duplicate_signal"),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "duplicate", "reason": "duplicate_signal"},
            )

        signal_id = cursor.lastrowid
        db.execute(
            """
            INSERT INTO runs (signal_id, dedupe_key, status, reason)
            VALUES (?, ?, ?, ?)
            """,
            (signal_id, dedupe_key, "accepted", None),
        )
        pipeline_state = SignalState(
            payload=payload,
            signal_id=signal_id,
            dedupe_key=dedupe_key,
            received_at=_now(),
        )
        pipeline_state = build_pipeline().run(pipeline_state, db, settings)

        log_audit(
            db,
            event_type="webhook",
            status_value="accepted",
            path_token_valid=True,
            payload_token_valid=True,
            source=payload.source.value,
            dedupe_key=dedupe_key,
        )

        return {
            "status": "accepted",
            "signal_id": signal_id,
            "dedupe_key": dedupe_key,
            "risk_decision": pipeline_state.risk_decision,
            "risk_reason_codes": pipeline_state.risk_reason_codes,
        }
