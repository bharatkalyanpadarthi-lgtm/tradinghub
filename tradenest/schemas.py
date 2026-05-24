from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SignalSource(str, Enum):
    tradingview = "TradingView"
    replay = "Replay"
    manual = "Manual"


class Candle(BaseModel):
    high: float = Field(allow_inf_nan=False)
    low: float = Field(allow_inf_nan=False)
    close: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_price_range(self) -> "Candle":
        if self.high < self.low:
            raise ValueError("candle_high_below_low")
        if not self.low <= self.close <= self.high:
            raise ValueError("candle_close_outside_range")
        return self


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_token: str = Field(min_length=1)
    source: SignalSource
    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell", "long", "short"]
    strategy: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    event_time: datetime
    alert_id: Optional[str] = Field(default=None, min_length=1)
    price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    candles: List[Candle] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SignalState(BaseModel):
    payload: WebhookPayload
    signal_id: int
    dedupe_key: str
    received_at: datetime
    atr: Optional[float] = None
    volatility: Dict[str, Any] = Field(default_factory=dict)
    feature_status: str = "pending"
    signal_valid: bool = False
    signal_grade: str = "ungraded"
    rubric_version: str = ""
    reason_codes: List[str] = Field(default_factory=list)
    risk_decision: Optional[str] = None
    risk_reason_codes: List[str] = Field(default_factory=list)
    run_id: Optional[int] = None
    paper_order_id: Optional[int] = None
    paper_order_status: Optional[str] = None
