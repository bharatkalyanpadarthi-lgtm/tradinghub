from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SignalSource(str, Enum):
    tradingview = "TradingView"
    replay = "Replay"
    manual = "Manual"


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
    price: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
