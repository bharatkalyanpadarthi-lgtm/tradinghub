# TradeNest Local Runbook

This runbook is for the local Mac mini paper-trading MVP. It assumes the repo lives at:

```bash
/Users/bharatmacmini/Documents/New project
```

## Environment

Create `.env` from `.env.example` and set at least:

```bash
TRADENEST_DB_PATH=./data/tradenest.sqlite3
TRADINGVIEW_PATH_TOKEN=...
TRADINGVIEW_AUTH_TOKEN=...
TRADENEST_TELEGRAM_ENABLED=false
```

If Telegram is enabled, also set:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=...
```

Validate the environment:

```bash
ops/scripts/validate_env.sh
```

## Start Backend Manually

```bash
cd "/Users/bharatmacmini/Documents/New project"
source .env
.venv/bin/python -m uvicorn tradenest.main:app --host 127.0.0.1 --port 8000
```

Check health:

```bash
curl -fsS http://127.0.0.1:8000/api/status
```

## Start Dashboard Manually

```bash
cd "/Users/bharatmacmini/Documents/New project/dashboard"
npm install
npm run build
NEXT_PUBLIC_TRADENEST_API_BASE=http://127.0.0.1:8000 npm run start -- --hostname 127.0.0.1 --port 3000
```

Open:

```text
http://127.0.0.1:3000
```

## Install launchd Services

Build the dashboard once before loading launchd:

```bash
cd "/Users/bharatmacmini/Documents/New project/dashboard"
npm install
npm run build
```

Install templates:

```bash
mkdir -p ~/Library/LaunchAgents
cp "/Users/bharatmacmini/Documents/New project/ops/launchd/tradenest-backend.plist" ~/Library/LaunchAgents/
cp "/Users/bharatmacmini/Documents/New project/ops/launchd/tradenest-dashboard.plist" ~/Library/LaunchAgents/
mkdir -p "/Users/bharatmacmini/Documents/New project/logs"
launchctl load ~/Library/LaunchAgents/tradenest-backend.plist
launchctl load ~/Library/LaunchAgents/tradenest-dashboard.plist
```

## Unload launchd Services

```bash
launchctl unload ~/Library/LaunchAgents/tradenest-dashboard.plist
launchctl unload ~/Library/LaunchAgents/tradenest-backend.plist
```

## Replay Dry Run

Use the committed sample file:

```bash
tradenest-replay \
  --file tradenest/replay/sample_signals.csv \
  --target http://127.0.0.1:8000 \
  --path-token "$TRADINGVIEW_PATH_TOKEN" \
  --payload-token "$TRADINGVIEW_AUTH_TOKEN" \
  --dry-run
```

Expected: payloads show `source = Replay`, `auth_token = [redacted]`, and `posted = 0`.

## Real Replay

```bash
tradenest-replay \
  --file tradenest/replay/sample_signals.csv \
  --target http://127.0.0.1:8000 \
  --path-token "$TRADINGVIEW_PATH_TOKEN" \
  --payload-token "$TRADINGVIEW_AUTH_TOKEN" \
  --speed 20 \
  --summary-file replay-summary.json
```

Expected sample behavior: rows are posted through the same webhook path. Duplicate replays return `409` and are counted as duplicates.

## Kill and Unkill

Dashboard/API:

```bash
curl -X POST http://127.0.0.1:8000/api/system/kill
curl -X POST http://127.0.0.1:8000/api/system/unkill
```

Telegram:

```text
/status
/kill
/unkill
```

After `/kill`, submit one replay signal and confirm the latest run has `risk_decision = blocked` with `kill_switch_enabled`.

## Verify Paper Exits

The automated tests cover:

- `stop_loss_hit`
- `take_profit_hit`
- `counter_signal`
- `time_exit`

Run:

```bash
.venv/bin/python -m pytest tests/test_paper_broker.py -q
```

For live paper validation, use current price movement or controlled test fixtures rather than waiting for market price to hit SL/TP.

## SQLite and Backups

Default database:

```text
./data/tradenest.sqlite3
```

Default backups:

```text
./backups/
```

Create a backup:

```bash
ops/scripts/backup_sqlite.sh
```

Healthcheck:

```bash
ops/scripts/healthcheck.sh
```

Rotate logs:

```bash
ops/scripts/rotate_logs.sh
```
