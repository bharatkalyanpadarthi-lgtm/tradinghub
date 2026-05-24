# TradeNest Local Runbook

This runbook is for the local Mac mini paper-trading MVP.

## Repo vs Runtime Layout

TradeNest runs in three distinct locations on the Mac mini. Keeping them
separate is what makes the launchd setup reliable.

| Role | Path | Notes |
| --- | --- | --- |
| Repo (source of truth) | `/Users/bharatmacmini/Documents/New project` | Git lives here. All edits, commits, and tags happen here. **macOS launchd cannot read this path.** |
| Runtime working dir | `~/tradenest-runtime` | Deployed copy of the repo that launchd is allowed to read. Backend and dashboard execute here. The active `.env` lives here. |
| Deployed launchd plists | `~/Library/LaunchAgents/` | Copies of `ops/launchd/*.plist`. macOS reads these to start the backend and dashboard at login. |

Rule of thumb: edit in the repo, sync to `~/tradenest-runtime`, then (if
plists changed) copy to `~/Library/LaunchAgents/` and reload launchd.

### Backend and Dashboard URLs

```text
Backend  http://127.0.0.1:8000
Dashboard http://127.0.0.1:3000
```

## Public Exposure (Cloudflare Tunnel + TradingView)

For the public webhook layer — exposing only `127.0.0.1:8000`'s
`/webhook/tradingview/{token}` path to the internet via Cloudflare
Tunnel, and configuring TradingView alerts to call it — see the
dedicated guide:

```text
docs/cloudflare-tradingview-setup.md
```

Key constraints (enforced by that guide):

- One public hostname only: `tradenest-webhook.<your-domain>` →
  `http://127.0.0.1:8000`. The dashboard stays private.
- Two-token auth: URL path token (`TRADINGVIEW_PATH_TOKEN`) plus
  in-body `auth_token` (`TRADINGVIEW_AUTH_TOKEN`).
- No Cloudflare Access service tokens on this hostname (TradingView
  cannot send the required headers).
- No WAF/transformations that modify path, query, headers, or body.
- Optional launchd templates for `cloudflared` live at
  `ops/scripts/run-cloudflared.sh` and
  `ops/launchd/tradenest-cloudflared.plist`. They are templates only;
  not auto-loaded.

## Environment

Create `.env` from `.env.example` in **the runtime working dir** and set
at least:

```bash
TRADENEST_DB_PATH=./data/tradenest.sqlite3
TRADENEST_ADMIN_TOKEN=...
TRADINGVIEW_PATH_TOKEN=...
TRADINGVIEW_AUTH_TOKEN=...
TRADENEST_TELEGRAM_ENABLED=false
```

If Telegram is enabled, also set:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=...
TRADENEST_TELEGRAM_WEBHOOK_SECRET_TOKEN=...
```

Validate the environment from the runtime dir:

```bash
cd ~/tradenest-runtime
ops/scripts/validate_env.sh
```

## Create or Update `~/tradenest-runtime`

The runtime directory is a deployable copy of the repo plus a populated
`.env` and the runtime-mutable `data/`, `logs/`, and `backups/` folders.

First-time setup:

```bash
mkdir -p ~/tradenest-runtime
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'node_modules' \
  --exclude 'data' \
  --exclude 'logs' \
  --exclude 'backups' \
  --exclude '.env' \
  "/Users/bharatmacmini/Documents/New project/" \
  ~/tradenest-runtime/

cd ~/tradenest-runtime
mkdir -p data logs backups
cp .env.example .env  # then edit .env to set real tokens
python3 -m venv .venv
.venv/bin/pip install -e .
cd dashboard && npm install && npm run build
```

Update after a repo change (re-sync code; preserve `.env`, `data/`,
`logs/`, `backups/`, `.venv`, `node_modules`):

```bash
rsync -a \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'node_modules' \
  --exclude 'data' \
  --exclude 'logs' \
  --exclude 'backups' \
  --exclude '.env' \
  "/Users/bharatmacmini/Documents/New project/" \
  ~/tradenest-runtime/
```

If `pyproject.toml` changed: `~/tradenest-runtime/.venv/bin/pip install -e .`
If `dashboard/` changed: `cd ~/tradenest-runtime/dashboard && npm install && npm run build`

## Start Backend Manually

```bash
cd ~/tradenest-runtime
set -a; source .env; set +a
.venv/bin/python -m uvicorn tradenest.main:app --host 127.0.0.1 --port 8000
```

Check health:

```bash
curl -fsS \
  -H "X-TradeNest-Admin-Token: $TRADENEST_ADMIN_TOKEN" \
  http://127.0.0.1:8000/api/status
```

## Start Dashboard Manually

```bash
cd ~/tradenest-runtime/dashboard
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
cd ~/tradenest-runtime/dashboard
npm install
npm run build
```

Copy plist templates from the repo into `~/Library/LaunchAgents/`:

```bash
mkdir -p ~/Library/LaunchAgents
cp "/Users/bharatmacmini/Documents/New project/ops/launchd/tradenest-backend.plist" ~/Library/LaunchAgents/
cp "/Users/bharatmacmini/Documents/New project/ops/launchd/tradenest-dashboard.plist" ~/Library/LaunchAgents/
mkdir -p ~/tradenest-runtime/logs
launchctl load ~/Library/LaunchAgents/tradenest-backend.plist
launchctl load ~/Library/LaunchAgents/tradenest-dashboard.plist
```

The plists call `~/tradenest-runtime/ops/scripts/run-backend.sh` and
`run-dashboard.sh`. Those wrappers cd into `~/tradenest-runtime`, source
`.env`, log a timestamped start line, and `exec` the real process so
launchd tracks the correct PID.

## Unload launchd Services

```bash
launchctl unload ~/Library/LaunchAgents/tradenest-dashboard.plist
launchctl unload ~/Library/LaunchAgents/tradenest-backend.plist
```

## Replay Dry Run

Use the committed sample file. The CLI accepts a numeric `--speed` only
(e.g. `--speed 20` for 20x, `--speed 0` for as-fast-as-possible). Do not
suffix with `x`.

```bash
cd ~/tradenest-runtime
set -a; source .env; set +a
tradenest-replay \
  --file tradenest/replay/sample_signals.csv \
  --target http://127.0.0.1:8000 \
  --path-token "$TRADINGVIEW_PATH_TOKEN" \
  --payload-token "$TRADINGVIEW_AUTH_TOKEN" \
  --speed 20 \
  --dry-run
```

Expected: payloads show `source = Replay`, `auth_token = [redacted]`, and
`posted = 0`.

## Run Tests

From the repo, run the full local verification suite:

```bash
ops/scripts/test_all.sh
```

This runs backend pytest, dashboard TypeScript checking, and the
dashboard production build. GitHub Actions runs the same checks on
pushes and pull requests to `main`.

## Real Replay

```bash
cd ~/tradenest-runtime
set -a; source .env; set +a
tradenest-replay \
  --file tradenest/replay/sample_signals.csv \
  --target http://127.0.0.1:8000 \
  --path-token "$TRADINGVIEW_PATH_TOKEN" \
  --payload-token "$TRADINGVIEW_AUTH_TOKEN" \
  --speed 20 \
  --summary-file replay-summary.json
```

For maximum throughput (no inter-row delay) use `--speed 0`:

```bash
tradenest-replay \
  --file tradenest/replay/sample_signals.csv \
  --target http://127.0.0.1:8000 \
  --path-token "$TRADINGVIEW_PATH_TOKEN" \
  --payload-token "$TRADINGVIEW_AUTH_TOKEN" \
  --speed 0 \
  --summary-file replay-summary.json
```

Expected sample behavior: rows are posted through the same webhook path.
Duplicate replays return `409` and are counted as duplicates.

Sample CSV:

```text
tradenest/replay/sample_signals.csv
```

## Kill and Unkill

Dashboard/API:

```bash
curl -X POST \
  -H "X-TradeNest-Admin-Token: $TRADENEST_ADMIN_TOKEN" \
  http://127.0.0.1:8000/api/system/kill
curl -X POST \
  -H "X-TradeNest-Admin-Token: $TRADENEST_ADMIN_TOKEN" \
  http://127.0.0.1:8000/api/system/unkill
```

Telegram:

```text
/status
/kill
/unkill
```

After `/kill`, submit one replay signal and confirm the latest run has
`risk_decision = blocked` with `kill_switch_enabled`.

## Verify Paper Exits

The automated tests cover:

- `stop_loss_hit`
- `take_profit_hit`
- `counter_signal`
- `time_exit`

Run from the repo:

```bash
cd "/Users/bharatmacmini/Documents/New project"
.venv/bin/python -m pytest tests/test_paper_broker.py -q
```

For live paper validation, use current price movement or controlled test
fixtures rather than waiting for market price to hit SL/TP.

## SQLite and Backups

Default database (relative to the runtime working dir):

```text
~/tradenest-runtime/data/tradenest.sqlite3
```

Default backups:

```text
~/tradenest-runtime/backups/
```

Create a backup:

```bash
cd ~/tradenest-runtime
ops/scripts/backup_sqlite.sh
```

Healthcheck:

```bash
cd ~/tradenest-runtime
ops/scripts/healthcheck.sh
```

Rotate logs:

```bash
cd ~/tradenest-runtime
ops/scripts/rotate_logs.sh
```
