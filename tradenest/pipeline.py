from __future__ import annotations

import sqlite3
from typing import Iterable

from tradenest.config import Settings
from tradenest.schemas import SignalState
from tradenest.stages.base import Stage
from tradenest.stages.market_features import MarketFeaturesStage
from tradenest.stages.risk_gate import RiskGateStage
from tradenest.stages.signal_engine import SignalEngineStage


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
            state = stage(state, db, settings)
        return state


def build_pipeline() -> Pipeline:
    return Pipeline(
        (
            MarketFeaturesStage(),
            SignalEngineStage(),
            RiskGateStage(),
        )
    )
