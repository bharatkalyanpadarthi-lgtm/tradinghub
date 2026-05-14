from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    db_path: str
    tradingview_path_token: str
    tradingview_auth_token: str
    tradingview_max_stale_seconds: int


def get_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("TRADENEST_DB_PATH", "./data/tradenest.sqlite3"),
        tradingview_path_token=os.environ.get("TRADINGVIEW_PATH_TOKEN", ""),
        tradingview_auth_token=os.environ.get("TRADINGVIEW_AUTH_TOKEN", ""),
        tradingview_max_stale_seconds=int(
            os.environ.get("TRADINGVIEW_MAX_STALE_SECONDS", "300")
        ),
    )
