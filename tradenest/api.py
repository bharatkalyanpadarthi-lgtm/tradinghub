from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import require_admin_request, require_telegram_webhook_secret
from .config import Settings, get_settings
from .db import log_audit, session
from .services.telegram_service import (
    handle_telegram_update,
    set_system_state,
    status_summary,
    system_state_bool,
    today_summary,
)


router = APIRouter()
api_router = APIRouter(prefix="/api", dependencies=[Depends(require_admin_request)])
telegram_router = APIRouter()


def _row_to_dict(row) -> Dict[str, Any]:
    return dict(row) if row is not None else {}


def _safe_signal(row) -> Dict[str, Any]:
    if row is None:
        return {}
    data = dict(row)
    data.pop("payload_json", None)
    return data


def _safe_stage_event(row) -> Dict[str, Any]:
    data = dict(row)
    payload = data.get("payload_json")
    if payload:
        data["payload"] = json.loads(payload)
    data.pop("payload_json", None)
    return data


def _reason_codes(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return [str(value)]
    return parsed if isinstance(parsed, list) else [str(parsed)]


def _journal_entries(db) -> list[Dict[str, Any]]:
    rows = db.execute(
        """
        SELECT
            paper_orders.opened_at_utc AS time,
            signals.source,
            paper_orders.symbol,
            paper_orders.side,
            paper_orders.strategy,
            runs.status AS final_decision,
            risk_decisions.reason_codes_json AS reason_codes_json,
            paper_orders.status AS paper_order_status,
            paper_orders.exit_reason,
            paper_orders.realized_pnl_eur AS pnl_eur,
            paper_orders.realized_pnl_percent AS pnl_percent,
            runs.id AS run_id
        FROM paper_orders
        LEFT JOIN signals ON signals.id = paper_orders.signal_id
        LEFT JOIN runs ON runs.id = paper_orders.run_id
        LEFT JOIN risk_decisions ON risk_decisions.signal_id = signals.id
        ORDER BY paper_orders.opened_at_utc DESC, paper_orders.id DESC
        """
    ).fetchall()
    entries = []
    for row in rows:
        data = dict(row)
        data["reason"] = ", ".join(_reason_codes(data.pop("reason_codes_json", None)))
        entries.append(data)
    return entries


@api_router.get("/status")
def get_status(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        summary = status_summary(db, settings)
    return {"backend_health": "ok", **summary}


@api_router.get("/risk/status")
def get_risk_status(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        today = today_summary(db, settings)
        open_positions = db.execute(
            "SELECT COUNT(*) FROM paper_orders WHERE status = 'open'"
        ).fetchone()[0]
        kill_switch = system_state_bool(db, "kill_switch", settings.kill_switch)
    today_pnl = float(today["paper_pnl_eur"])
    return {
        "daily_loss_cap_eur": settings.daily_loss_cap_eur,
        "today_paper_pnl_eur": today_pnl,
        "remaining_daily_risk_eur": settings.daily_loss_cap_eur + min(today_pnl, 0),
        "max_open_positions": settings.max_open_positions,
        "current_open_positions": open_positions,
        "allowed_symbols": list(settings.allowed_symbols),
        "allowed_strategies": [settings.strategy],
        "cooldown_minutes": settings.cooldown_minutes,
        "kill_switch": kill_switch,
        "mode": settings.mode,
    }


@api_router.get("/system/state")
def get_system_state(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        rows = db.execute("SELECT key, value, updated_at FROM system_state").fetchall()
        kill_switch = system_state_bool(db, "kill_switch", settings.kill_switch)
    return {
        "kill_switch": kill_switch,
        "state": [dict(row) for row in rows],
    }


@api_router.post("/system/kill")
def kill_system(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        set_system_state(db, "kill_switch", "true")
        log_audit(db, event_type="dashboard", status_value="accepted", reason="kill")
    return {"kill_switch": True}


@api_router.post("/system/unkill")
def unkill_system(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        set_system_state(db, "kill_switch", "false")
        log_audit(db, event_type="dashboard", status_value="accepted", reason="unkill")
    return {"kill_switch": False}


@api_router.get("/runs")
def list_runs(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        rows = db.execute(
            """
            SELECT
                runs.id,
                runs.status,
                runs.reason,
                runs.created_at,
                signals.source,
                signals.symbol,
                signals.side,
                signals.strategy,
                risk_decisions.decision AS risk_decision,
                risk_decisions.signal_grade,
                risk_decisions.reason_codes_json,
                paper_orders.status AS paper_order_status
            FROM runs
            LEFT JOIN signals ON signals.id = runs.signal_id
            LEFT JOIN risk_decisions ON risk_decisions.signal_id = signals.id
            LEFT JOIN paper_orders ON paper_orders.run_id = runs.id
            ORDER BY runs.id DESC
            LIMIT 50
            """
        ).fetchall()
    runs = []
    for row in rows:
        data = dict(row)
        data["reason_codes"] = _reason_codes(data.pop("reason_codes_json", None))
        runs.append(data)
    return {"runs": runs}


@api_router.get("/runs/{run_id}")
def get_run(run_id: int, settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail={"reason": "run_not_found"})

        signal = None
        if run["signal_id"] is not None:
            signal = db.execute(
                "SELECT * FROM signals WHERE id = ?",
                (run["signal_id"],),
            ).fetchone()

        risk_decision = db.execute(
            "SELECT * FROM risk_decisions WHERE signal_id = ? ORDER BY id DESC LIMIT 1",
            (run["signal_id"],),
        ).fetchone()
        paper_orders = db.execute(
            "SELECT * FROM paper_orders WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        stage_events = db.execute(
            "SELECT * FROM stage_events WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()

    return {
        "run": _row_to_dict(run),
        "signal": _safe_signal(signal),
        "risk_decision": _row_to_dict(risk_decision),
        "paper_orders": [dict(row) for row in paper_orders],
        "stage_events": [_safe_stage_event(row) for row in stage_events],
    }


@api_router.get("/journal")
def get_journal(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        rows = db.execute(
            """
            SELECT *
            FROM paper_orders
            ORDER BY opened_at_utc DESC, id DESC
            """
        ).fetchall()
        entries = _journal_entries(db)
    return {"paper_orders": [dict(row) for row in rows], "entries": entries}


@telegram_router.post(
    "/telegram/webhook",
    dependencies=[Depends(require_telegram_webhook_secret)],
)
async def telegram_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    try:
        update = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail={"status": "rejected", "reason": "invalid_json_body"},
        )
    handled = handle_telegram_update(update, settings)
    return {"handled": handled}


router.include_router(api_router)
router.include_router(telegram_router)
