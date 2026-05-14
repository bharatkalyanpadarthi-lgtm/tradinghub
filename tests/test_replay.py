from __future__ import annotations

from pathlib import Path

from tradenest.replay.runner import read_rows, row_to_payload, run_replay


def sample_row(**overrides):
    row = {
        "timestamp": "2020-01-01T00:00:00Z",
        "strategy_id": "cvd_rubric_v1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "signal_type": "ENTRY",
        "timeframe": "15m",
        "bar_id": "BTCUSDT-15m-old",
        "price": "65000",
        "atr": "120",
    }
    row.update(overrides)
    return row


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    columns = "timestamp,strategy_id,symbol,side,signal_type,timeframe,bar_id,price,atr"
    lines = [columns]
    for row in rows:
        lines.append(",".join(row[column] for column in columns.split(",")))
    path.write_text("\n".join(lines) + "\n")
    return path


def test_csv_row_converts_to_valid_webhook_payload():
    payload = row_to_payload(sample_row(), "payload-secret")

    assert payload["auth_token"] == "payload-secret"
    assert payload["source"] == "Replay"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["side"] == "buy"
    assert payload["strategy"] == "cvd_rubric_v1"
    assert payload["event_time"] == "2020-01-01T00:00:00+00:00"
    assert payload["alert_id"] == "BTCUSDT-15m-old"
    assert payload["metadata"]["atr_fixture"] == 120


def test_read_rows_limit_symbol_and_strategy_filters(tmp_path):
    csv_path = write_csv(
        tmp_path / "signals.csv",
        [
            sample_row(symbol="BTCUSDT", bar_id="one"),
            sample_row(symbol="ETHUSDT", bar_id="two"),
            sample_row(symbol="BTCUSDT", strategy_id="other", bar_id="three"),
        ],
    )

    rows = read_rows(csv_path, limit=1, symbol="BTCUSDT", strategy="cvd_rubric_v1")

    assert len(rows) == 1
    assert rows[0]["bar_id"] == "one"


def test_dry_run_does_not_post(tmp_path):
    csv_path = write_csv(tmp_path / "signals.csv", [sample_row(), sample_row(bar_id="two")])
    calls = []
    printed = []

    summary = run_replay(
        csv_path=csv_path,
        target="http://testserver",
        path_token="path-secret",
        payload_token="payload-secret",
        dry_run=True,
        poster=lambda url, payload: calls.append((url, payload)) or (200, {}),
        printer=printed.append,
    )

    assert calls == []
    assert summary.rows_read == 2
    assert summary.posted == 0
    assert '"source": "Replay"' in printed[0]
    assert "payload-secret" not in printed[0]


def test_limit_replays_only_first_n_rows(tmp_path):
    csv_path = write_csv(
        tmp_path / "signals.csv",
        [sample_row(bar_id="one"), sample_row(bar_id="two"), sample_row(bar_id="three")],
    )
    calls = []

    summary = run_replay(
        csv_path=csv_path,
        target="http://testserver",
        path_token="path-secret",
        payload_token="payload-secret",
        limit=2,
        poster=lambda url, payload: calls.append(payload) or (200, {"status": "accepted"}),
        printer=lambda text: None,
    )

    assert len(calls) == 2
    assert summary.rows_read == 2
    assert summary.posted == 2
    assert summary.accepted == 2


def test_duplicate_replay_row_is_handled(tmp_path):
    csv_path = write_csv(tmp_path / "signals.csv", [sample_row(), sample_row(bar_id="dupe")])
    responses = [(200, {"status": "accepted"}), (409, {"detail": {"status": "duplicate"}})]

    summary = run_replay(
        csv_path=csv_path,
        target="http://testserver",
        path_token="path-secret",
        payload_token="payload-secret",
        poster=lambda url, payload: responses.pop(0),
        printer=lambda text: None,
    )

    assert summary.accepted == 1
    assert summary.duplicates == 1
    assert summary.rejected == 0
    assert summary.errors == 0


def test_replay_summary_counts_accepted_rejected_duplicates_and_errors(tmp_path):
    csv_path = write_csv(
        tmp_path / "signals.csv",
        [
            sample_row(bar_id="accepted"),
            sample_row(bar_id="duplicate"),
            sample_row(bar_id="rejected"),
            sample_row(bar_id="error"),
        ],
    )
    responses = [
        (200, {"status": "accepted"}),
        (409, {"detail": {"status": "duplicate"}}),
        (401, {"detail": {"reason": "invalid_payload_auth_token"}}),
        (0, {"error": "connection refused"}),
    ]
    summary_file = tmp_path / "summary.json"

    summary = run_replay(
        csv_path=csv_path,
        target="http://testserver",
        path_token="path-secret",
        payload_token="payload-secret",
        poster=lambda url, payload: responses.pop(0),
        summary_path=summary_file,
        printer=lambda text: None,
    )

    assert summary.posted == 4
    assert summary.accepted == 1
    assert summary.duplicates == 1
    assert summary.rejected == 1
    assert summary.errors == 1
    assert '"accepted": 1' in summary_file.read_text()


def test_stale_replay_payload_is_accepted_through_existing_webhook(client, settings):
    payload = row_to_payload(sample_row(), settings.tradingview_auth_token)

    response = client.post(
        f"/webhook/tradingview/{settings.tradingview_path_token}",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["risk_decision"] == "passed"
