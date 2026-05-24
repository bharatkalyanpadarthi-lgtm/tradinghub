from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from .config import Settings, get_settings
from .db import log_audit, session, transaction
from .pipeline import build_pipeline
from .schemas import SignalSource, SignalState, WebhookPayload
from .services.telegram_service import TelegramNotifier


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
            body = await request.json()
        except json.JSONDecodeError:
            log_audit(
                db,
                event_type="validation",
                status_value="rejected",
                reason="invalid_json_body",
                path_token_valid=True,
            )
            raise HTTPException(
                status_code=422,
                detail={"status": "rejected", "reason": "invalid_payload_schema"},
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

        notifier = TelegramNotifier(settings)
        duplicate_signal = False
        pipeline_error: Exception | None = None
        response_body: Dict[str, Any] | None = None
        pipeline_state: SignalState | None = None

        with transaction(db, immediate=True):
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
                duplicate_signal = True
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
            else:
                signal_id = cursor.lastrowid
                run_cursor = db.execute(
                    """
                    INSERT INTO runs (signal_id, dedupe_key, status, reason)
                    VALUES (?, ?, ?, ?)
                    """,
                    (signal_id, dedupe_key, "accepted", None),
                )
                run_id = run_cursor.lastrowid
                pipeline_state = SignalState(
                    payload=payload,
                    signal_id=signal_id,
                    dedupe_key=dedupe_key,
                    run_id=run_id,
                    received_at=_now(),
                )
                try:
                    pipeline_state = build_pipeline().run(pipeline_state, db, settings)
                except Exception as exc:
                    pipeline_error = exc
                    db.execute(
                        """
                        UPDATE runs
                        SET status = ?, reason = ?
                        WHERE id = ?
                        """,
                        ("error", exc.__class__.__name__, run_id),
                    )
                    log_audit(
                        db,
                        event_type="pipeline",
                        status_value="error",
                        reason=exc.__class__.__name__,
                        path_token_valid=True,
                        payload_token_valid=True,
                        source=payload.source.value,
                        dedupe_key=dedupe_key,
                    )
                else:
                    log_audit(
                        db,
                        event_type="webhook",
                        status_value="accepted",
                        path_token_valid=True,
                        payload_token_valid=True,
                        source=payload.source.value,
                        dedupe_key=dedupe_key,
                    )
                    response_body = {
                        "status": "accepted",
                        "run_id": run_id,
                        "signal_id": signal_id,
                        "dedupe_key": dedupe_key,
                        "risk_decision": pipeline_state.risk_decision,
                        "risk_reason_codes": pipeline_state.risk_reason_codes,
                        "paper_order_id": pipeline_state.paper_order_id,
                        "paper_order_status": pipeline_state.paper_order_status,
                    }

        if duplicate_signal:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "duplicate", "reason": "duplicate_signal"},
            )

        if pipeline_error is not None:
            notifier.system_error(pipeline_error.__class__.__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "reason": "pipeline_error",
                    "error_type": pipeline_error.__class__.__name__,
                },
            )

        if pipeline_state is None or response_body is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "error", "reason": "pipeline_missing_response"},
            )

        if pipeline_state.risk_decision == "blocked":
            notifier.signal_blocked(
                symbol=payload.symbol,
                side=payload.side,
                reason_codes=pipeline_state.risk_reason_codes,
            )
        else:
            notifier.signal_accepted(
                signal_id=signal_id,
                symbol=payload.symbol,
                side=payload.side,
            )

        return response_body
