from __future__ import annotations

import pytest

from tradenest.db import session
from tradenest.pipeline import build_pipeline as real_build_pipeline


pytestmark = pytest.mark.integration


def post_signal(client, settings, payload):
    return client.post(
        f"/webhook/tradingview/{settings.tradingview_path_token}",
        json=payload,
    )


def test_pipeline_error_is_recorded_and_next_signal_can_recover(
    client,
    settings,
    payload,
    monkeypatch,
):
    class FailsOncePipeline:
        calls = 0

        def run(self, state, db, settings):
            type(self).calls += 1
            if type(self).calls == 1:
                raise RuntimeError("temporary_failure")
            return real_build_pipeline().run(state, db, settings)

    monkeypatch.setattr("tradenest.webhook.build_pipeline", lambda: FailsOncePipeline())

    failed = post_signal(client, settings, payload)
    payload["alert_id"] = "tv-alert-recovery"
    recovered = post_signal(client, settings, payload)

    assert failed.status_code == 500
    assert failed.json()["detail"]["error_type"] == "RuntimeError"
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "accepted"
    assert recovered.json()["risk_decision"] == "passed"

    with session(settings.db_path) as db:
        runs = db.execute("SELECT status, reason FROM runs ORDER BY id").fetchall()
        orders = db.execute("SELECT status FROM paper_orders ORDER BY id").fetchall()

    assert [dict(row) for row in runs] == [
        {"status": "error", "reason": "RuntimeError"},
        {"status": "accepted", "reason": None},
    ]
    assert [row["status"] for row in orders] == ["open"]


def test_public_surface_fails_closed_while_tradingview_webhook_still_works(
    client,
    settings,
    payload,
):
    public_status = client.get(
        "/api/status",
        headers={"X-TradeNest-Admin-Token": "wrong"},
    )
    webhook_response = post_signal(client, settings, payload)

    assert public_status.status_code == 401
    assert public_status.json()["detail"]["reason"] == "invalid_admin_token"
    assert webhook_response.status_code == 200
    assert webhook_response.json()["status"] == "accepted"
