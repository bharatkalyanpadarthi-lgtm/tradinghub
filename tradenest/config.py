from dataclasses import dataclass
import os
from typing import Tuple


def _parse_csv(value: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: str
    tradingview_path_token: str
    tradingview_auth_token: str
    tradingview_max_stale_seconds: int
    timezone: str
    mode: str
    daily_loss_cap_eur: float
    max_open_positions: int
    strategy: str
    allowed_symbols: Tuple[str, ...]
    cooldown_minutes: int
    max_trades_per_day: int
    atr_period: int
    kill_switch: bool


def get_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("TRADENEST_DB_PATH", "./data/tradenest.sqlite3"),
        tradingview_path_token=os.environ.get("TRADINGVIEW_PATH_TOKEN", ""),
        tradingview_auth_token=os.environ.get("TRADINGVIEW_AUTH_TOKEN", ""),
        tradingview_max_stale_seconds=int(
            os.environ.get("TRADINGVIEW_MAX_STALE_SECONDS", "300")
        ),
        timezone=os.environ.get("TRADENEST_TIMEZONE", "Europe/Amsterdam"),
        mode=os.environ.get("TRADENEST_MODE", "paper"),
        daily_loss_cap_eur=float(os.environ.get("TRADENEST_DAILY_LOSS_CAP_EUR", "50")),
        max_open_positions=int(os.environ.get("TRADENEST_MAX_OPEN_POSITIONS", "1")),
        strategy=os.environ.get("TRADENEST_STRATEGY", "cvd_rubric_v1"),
        allowed_symbols=_parse_csv(
            os.environ.get("TRADENEST_ALLOWED_SYMBOLS", "BTCUSDT,ETHUSDT")
        ),
        cooldown_minutes=int(os.environ.get("TRADENEST_COOLDOWN_MINUTES", "15")),
        max_trades_per_day=int(os.environ.get("TRADENEST_MAX_TRADES_PER_DAY", "3")),
        atr_period=int(os.environ.get("TRADENEST_ATR_PERIOD", "14")),
        kill_switch=_parse_bool(os.environ.get("TRADENEST_KILL_SWITCH", "false")),
    )
