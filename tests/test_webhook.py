from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradenest.db import migrate, session


def post_signal(client, settings, payload, path_token=None):
    token = path_token if path_token is not None else settings.tradingview_path_token
    return client.post(f"/webhook/tradingview/{token}", json=payload)


def count_rows(settings, table):
    with session(settings.db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_valid_tradingview_payload_is_accepted(client, settings, payload):
    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert count_rows(settings, "signals") == 1
    assert count_rows(settings, "runs") == 1
    assert count_rows(settings, "audit_logs") == 1


def test_invalid_path_token_is_rejected(client, settings, payload):
    response = post_signal(client, settings, payload, path_token="wrong")

    assert response.status_code == 401
    assert count_rows(settings, "signals") == 0
    with session(settings.db_path) as db:
        row = db.execute("SELECT reason FROM audit_logs").fetchone()
    assert row["reason"] == "invalid_path_token"


def test_invalid_payload_auth_token_is_rejected(client, settings, payload):
    payload["auth_token"] = "wrong"

    response = post_signal(client, settings, payload)

    assert response.status_code == 401
    assert count_rows(settings, "signals") == 0
    with session(settings.db_path) as db:
        row = db.execute("SELECT reason FROM audit_logs").fetchone()
    assert row["reason"] == "invalid_payload_auth_token"


def test_invalid_schema_is_rejected(client, settings, payload):
    del payload["symbol"]

    response = post_signal(client, settings, payload)

    assert response.status_code == 422
    assert count_rows(settings, "signals") == 0
    with session(settings.db_path) as db:
        row = db.execute("SELECT reason FROM audit_logs").fetchone()
    assert row["reason"] == "invalid_payload_schema"


def test_stale_tradingview_payload_is_rejected(client, settings, payload):
    payload["event_time"] = (
        datetime.now(timezone.utc) - timedelta(seconds=600)
    ).isoformat()

    response = post_signal(client, settings, payload)

    assert response.status_code == 422
    assert count_rows(settings, "signals") == 0
    with session(settings.db_path) as db:
        row = db.execute("SELECT reason FROM audit_logs").fetchone()
    assert row["reason"] == "stale_tradingview_signal"


def test_stale_replay_payload_is_accepted(client, settings, payload):
    payload["source"] = "Replay"
    payload["event_time"] = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert count_rows(settings, "signals") == 1


def test_stale_manual_payload_is_accepted(client, settings, payload):
    payload["source"] = "Manual"
    payload["event_time"] = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()

    response = post_signal(client, settings, payload)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert count_rows(settings, "signals") == 1


def test_duplicate_payload_returns_conflict_and_no_second_signal(client, settings, payload):
    first = post_signal(client, settings, payload)
    second = post_signal(client, settings, payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["status"] == "duplicate"
    assert count_rows(settings, "signals") == 1
    with session(settings.db_path) as db:
        audit_row = db.execute(
            "SELECT event_type, status, reason FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert dict(audit_row) == {
        "event_type": "dedupe",
        "status": "duplicate",
        "reason": "duplicate_signal",
    }


def test_sqlite_pragmas_and_required_tables(settings):
    with session(settings.db_path) as db:
        migrate(db)
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_keys").fetchone()[0]

    assert {
        "signals",
        "runs",
        "audit_logs",
        "system_state",
        "risk_decisions",
    }.issubset(table_names)
    assert journal_mode == "wal"
    assert busy_timeout == 5000
    assert foreign_keys == 1
