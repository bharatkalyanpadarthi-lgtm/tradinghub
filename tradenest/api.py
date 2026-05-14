from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from .config import Settings, get_settings
from .db import session
from .services.telegram_service import handle_telegram_update


router = APIRouter()


def _row_to_dict(row) -> Dict[str, Any]:
    return dict(row) if row is not None else {}


@router.get("/api/runs/{run_id}")
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
        "signal": _row_to_dict(signal),
        "risk_decision": _row_to_dict(risk_decision),
        "paper_orders": [dict(row) for row in paper_orders],
        "stage_events": [dict(row) for row in stage_events],
    }


@router.get("/api/journal")
def get_journal(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    with session(settings.db_path) as db:
        rows = db.execute(
            """
            SELECT *
            FROM paper_orders
            ORDER BY opened_at_utc DESC, id DESC
            """
        ).fetchall()
    return {"paper_orders": [dict(row) for row in rows]}


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    handled = handle_telegram_update(await request.json(), settings)
    return {"handled": handled}
