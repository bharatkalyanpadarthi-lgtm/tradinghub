from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from tradenest.config import Settings
from tradenest.services.price_feed import poll_open_paper_orders_once


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    if settings.price_feed_enabled:
        scheduler.add_job(
            poll_open_paper_orders_once,
            "interval",
            seconds=settings.price_feed_poll_interval_seconds,
            args=[settings],
            id="bybit_public_rest_price_feed",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    return scheduler


def start_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = build_scheduler(settings)
    scheduler.start()
    return scheduler
