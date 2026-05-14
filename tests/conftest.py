from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from tradenest.config import Settings, get_settings
from tradenest.db import migrate, session
from tradenest.main import create_app


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        db_path=str(tmp_path / "tradenest.sqlite3"),
        tradingview_path_token="path-secret",
        tradingview_auth_token="payload-secret",
        tradingview_max_stale_seconds=300,
        timezone="Europe/Amsterdam",
        mode="paper",
        daily_loss_cap_eur=50,
        max_open_positions=1,
        strategy="cvd_rubric_v1",
        allowed_symbols=("BTCUSDT", "ETHUSDT"),
        cooldown_minutes=15,
        max_trades_per_day=3,
        atr_period=14,
        kill_switch=False,
    )


@pytest.fixture()
def client(settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with session(settings.db_path) as db:
        migrate(db)
    return TestClient(app)


@pytest.fixture()
def payload(settings):
    return {
        "auth_token": settings.tradingview_auth_token,
        "source": "TradingView",
        "symbol": "BTCUSDT",
        "side": "buy",
        "strategy": "cvd_rubric_v1",
        "timeframe": "5m",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "alert_id": "tv-alert-1",
        "price": 65000.0,
        "metadata": {"atr_fixture": 125.5},
    }


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "TRADENEST_DB_PATH",
        "TRADINGVIEW_PATH_TOKEN",
        "TRADINGVIEW_AUTH_TOKEN",
        "TRADINGVIEW_MAX_STALE_SECONDS",
        "TRADENEST_TIMEZONE",
        "TRADENEST_MODE",
        "TRADENEST_DAILY_LOSS_CAP_EUR",
        "TRADENEST_MAX_OPEN_POSITIONS",
        "TRADENEST_STRATEGY",
        "TRADENEST_ALLOWED_SYMBOLS",
        "TRADENEST_COOLDOWN_MINUTES",
        "TRADENEST_MAX_TRADES_PER_DAY",
        "TRADENEST_ATR_PERIOD",
        "TRADENEST_KILL_SWITCH",
    ):
        monkeypatch.delenv(name, raising=False)
