from __future__ import annotations

import math
import sqlite3
from typing import Optional

from tradenest.config import Settings
from tradenest.schemas import Candle, SignalState


def _true_range(candle: Candle, previous_close: Optional[float]) -> float:
    high_low = candle.high - candle.low
    if previous_close is None:
        return high_low
    return max(high_low, abs(candle.high - previous_close), abs(candle.low - previous_close))


def calculate_atr(candles: list[Candle], period: int) -> Optional[float]:
    if period <= 0 or len(candles) < period:
        return None

    ranges = []
    previous_close = None
    for candle in candles:
        ranges.append(_true_range(candle, previous_close))
        previous_close = candle.close

    return sum(ranges[-period:]) / period


def _fixture_atr(state: SignalState) -> Optional[float]:
    value = state.payload.metadata.get("atr_fixture")
    if value is None:
        value = state.payload.metadata.get("atr")
    if value is None:
        return None
    try:
        atr = float(value)
    except (TypeError, ValueError):
        return None
    return atr if math.isfinite(atr) else None


class MarketFeaturesStage:
    def __call__(
        self,
        state: SignalState,
        db: sqlite3.Connection,
        settings: Settings,
    ) -> SignalState:
        atr = calculate_atr(state.payload.candles, settings.atr_period)
        feature_status = "calculated"

        if atr is None:
            atr = _fixture_atr(state)
            feature_status = "fixture" if atr is not None else "missing"

        state.atr = atr
        state.feature_status = feature_status
        state.volatility = {
            "atr": atr,
            "atr_period": settings.atr_period,
            "candle_count": len(state.payload.candles),
            "feature_status": feature_status,
        }
        return state
