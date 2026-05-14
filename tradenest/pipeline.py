from __future__ import annotations

import sqlite3
import json
from typing import Iterable

from tradenest.config import Settings
from tradenest.schemas import SignalState
from tradenest.stages.base import Stage
from tradenest.stages.market_features import MarketFeaturesStage
from tradenest.stages.paper_broker import PaperBrokerStage
from tradenest.stages.risk_gate import RiskGateStage
from tradenest.stages.signal_engine import SignalEngineStage


def _stage_name(stage: Stage) -> str:
    return stage.__class__.__name__


def _record_stage_event(
    db: sqlite3.Connection,
    *,
    state: SignalState,
    stage_name: str,
    status: str,
    reason: str | None = None,
) -> None:
    payload = {
        "feature_status": state.feature_status,
        "atr": state.atr,
        "signal_valid": state.signal_valid,
        "risk_decision": state.risk_decision,
        "paper_order_id": state.paper_order_id,
        "paper_order_status": state.paper_order_status,
    }
    db.execute(
        """
        INSERT INTO stage_events (
            run_id,
            signal_id,
            dedupe_key,
            stage_name,
            status,
            reason,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state.run_id,
            state.signal_id,
            state.dedupe_key,
            stage_name,
            status,
            reason,
            json.dumps(payload, sort_keys=True),
        ),
    )


class Pipeline:
    def __init__(self, stages: Iterable[Stage]):
        self._stages = tuple(stages)

    def run(
        self,
        state: SignalState,
        db: sqlite3.Connection,
        settings: Settings,
    ) -> SignalState:
        for stage in self._stages:
            name = _stage_name(stage)
            try:
                state = stage(state, db, settings)
            except Exception as exc:
                _record_stage_event(
                    db,
                    state=state,
                    stage_name=name,
                    status="error",
                    reason=exc.__class__.__name__,
                )
                raise
            _record_stage_event(
                db,
                state=state,
                stage_name=name,
                status="completed",
            )
        return state


def build_pipeline() -> Pipeline:
    return Pipeline(
        (
            MarketFeaturesStage(),
            SignalEngineStage(),
            RiskGateStage(),
            PaperBrokerStage(),
        )
    )
