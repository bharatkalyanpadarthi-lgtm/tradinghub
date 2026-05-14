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
    stop_loss_atr_multiplier: float
    take_profit_atr_multiplier: float
    default_quantity_eur: float
    close_on_counter_signal: bool
    max_holding_bars: int
    position_mode: str
    price_feed_enabled: bool
    price_feed_provider: str
    price_feed_category: str
    price_feed_base_url: str
    price_feed_poll_interval_seconds: int
    price_feed_request_timeout_seconds: int
    scheduler_autostart: bool
    telegram_enabled: bool
    telegram_bot_token_env: str
    telegram_allowed_chat_id_env: str
    telegram_bot_token: str
    telegram_allowed_chat_id: str


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
        stop_loss_atr_multiplier=float(
            os.environ.get("TRADENEST_STOP_LOSS_ATR_MULTIPLIER", "1.5")
        ),
        take_profit_atr_multiplier=float(
            os.environ.get("TRADENEST_TAKE_PROFIT_ATR_MULTIPLIER", "2.5")
        ),
        default_quantity_eur=float(os.environ.get("TRADENEST_DEFAULT_QUANTITY_EUR", "100")),
        close_on_counter_signal=_parse_bool(
            os.environ.get("TRADENEST_CLOSE_ON_COUNTER_SIGNAL", "true")
        ),
        max_holding_bars=int(os.environ.get("TRADENEST_MAX_HOLDING_BARS", "20")),
        position_mode=os.environ.get("TRADENEST_POSITION_MODE", "one_way"),
        price_feed_enabled=_parse_bool(os.environ.get("TRADENEST_PRICE_FEED_ENABLED", "true")),
        price_feed_provider=os.environ.get(
            "TRADENEST_PRICE_FEED_PROVIDER", "bybit_public_rest"
        ),
        price_feed_category=os.environ.get("TRADENEST_PRICE_FEED_CATEGORY", "linear"),
        price_feed_base_url=os.environ.get(
            "TRADENEST_PRICE_FEED_BASE_URL", "https://api.bybit.com"
        ),
        price_feed_poll_interval_seconds=int(
            os.environ.get("TRADENEST_PRICE_FEED_POLL_INTERVAL_SECONDS", "30")
        ),
        price_feed_request_timeout_seconds=int(
            os.environ.get("TRADENEST_PRICE_FEED_REQUEST_TIMEOUT_SECONDS", "5")
        ),
        scheduler_autostart=_parse_bool(
            os.environ.get("TRADENEST_SCHEDULER_AUTOSTART", "false")
        ),
        telegram_enabled=_parse_bool(os.environ.get("TRADENEST_TELEGRAM_ENABLED", "true")),
        telegram_bot_token_env=os.environ.get(
            "TRADENEST_TELEGRAM_BOT_TOKEN_ENV", "TELEGRAM_BOT_TOKEN"
        ),
        telegram_allowed_chat_id_env=os.environ.get(
            "TRADENEST_TELEGRAM_ALLOWED_CHAT_ID_ENV", "TELEGRAM_ALLOWED_CHAT_ID"
        ),
        telegram_bot_token=os.environ.get(
            os.environ.get("TRADENEST_TELEGRAM_BOT_TOKEN_ENV", "TELEGRAM_BOT_TOKEN"),
            "",
        ),
        telegram_allowed_chat_id=os.environ.get(
            os.environ.get(
                "TRADENEST_TELEGRAM_ALLOWED_CHAT_ID_ENV",
                "TELEGRAM_ALLOWED_CHAT_ID",
            ),
            "",
        ),
    )
