# TradeNest Operations Checklist

## Layout Sanity Check (run any time something feels off)

- Confirm repo source exists at `/Users/bharatmacmini/Documents/New project` and `git status` is clean (or expected).
- Confirm runtime copy exists at `~/tradenest-runtime` and is in sync with the repo (no expected files missing).
- Confirm `.env` exists at `~/tradenest-runtime/.env` (run `ops/scripts/validate_env.sh` from the runtime dir).
- Confirm both deployed plists exist:
  - `~/Library/LaunchAgents/tradenest-backend.plist`
  - `~/Library/LaunchAgents/tradenest-dashboard.plist`
- Confirm both deployed plists point at `~/tradenest-runtime`:
  - `grep -F WorkingDirectory ~/Library/LaunchAgents/tradenest-backend.plist` → `/Users/bharatmacmini/tradenest-runtime`
  - `grep -F WorkingDirectory ~/Library/LaunchAgents/tradenest-dashboard.plist` → `/Users/bharatmacmini/tradenest-runtime/dashboard`
- Confirm both wrappers exist and are executable:
  - `~/tradenest-runtime/ops/scripts/run-backend.sh`
  - `~/tradenest-runtime/ops/scripts/run-dashboard.sh`

## Daily Check

- Run `ops/scripts/healthcheck.sh` from `~/tradenest-runtime`.
- Confirm backend health responds: `curl -fsS http://127.0.0.1:8000/api/status`.
- Confirm dashboard reachable at `http://127.0.0.1:3000`.
- Open Mission Control and confirm backend health is `ok`.
- Check `/status` in Telegram if enabled.
- Confirm kill switch is clear unless intentionally enabled.
- Review today's signal count, blocked count, open positions, and paper P&L.
- Confirm no unexpected duplicate bursts in replay or webhook runs.

## Weekly Check

- Run `ops/scripts/backup_sqlite.sh` from `~/tradenest-runtime`.
- Confirm a fresh backup exists in `~/tradenest-runtime/backups/`.
- Run `ops/scripts/rotate_logs.sh` from `~/tradenest-runtime`.
- Run a replay smoke test from `~/tradenest-runtime`:
  ```bash
  set -a; source .env; set +a
  tradenest-replay \
    --file tradenest/replay/sample_signals.csv \
    --target http://127.0.0.1:8000 \
    --path-token "$TRADINGVIEW_PATH_TOKEN" \
    --payload-token "$TRADINGVIEW_AUTH_TOKEN" \
    --speed 20 \
    --dry-run
  ```
- Run backend tests from the repo: `.venv/bin/python -m pytest -q`.
- Build dashboard from the repo: `cd dashboard && npm run build`.
- Review Trade Journal for closed positions and P&L sanity.

## Before Reboot

- Confirm latest backup exists in `~/tradenest-runtime/backups/`.
- Confirm no critical paper validation run is in progress.
- Note current kill switch state.
- Unload launchd services if doing maintenance:
  - `launchctl unload ~/Library/LaunchAgents/tradenest-dashboard.plist`
  - `launchctl unload ~/Library/LaunchAgents/tradenest-backend.plist`

## After Reboot

- Confirm launchd services are loaded or start them manually.
- Run `ops/scripts/healthcheck.sh` from `~/tradenest-runtime`.
- Open dashboard at `http://127.0.0.1:3000`.
- Call `curl -fsS http://127.0.0.1:8000/api/status`.
- Send Telegram `/status` if Telegram is enabled.
- Run one replay dry-run using `tradenest/replay/sample_signals.csv` with `--speed 20 --dry-run`.

## After Updating Repo Plists or Wrapper Scripts

- Sync the change into the runtime: `rsync -a` repo → `~/tradenest-runtime` (excluding `.env`, `data/`, `logs/`, `backups/`, `.venv`, `node_modules`).
- Copy any updated plists into `~/Library/LaunchAgents/`.
- `launchctl unload` then `launchctl load` the affected plist.
- Re-run healthcheck and a replay dry-run to confirm the service still behaves.

## Cloudflare / TradingView Paper-Mode Checklist

Run this before pointing a real TradingView alert at the public webhook, and any time the tunnel or tokens change. Full procedures live in `docs/cloudflare-tradingview-setup.md`; this list is the gating one.

- Backend reachable locally: `curl -fsS http://127.0.0.1:8000/api/status` → `backend_health: ok`.
- `~/tradenest-runtime/ops/scripts/healthcheck.sh` exits 0.
- Cloudflare tunnel connector status is **Healthy** (dashboard or `cloudflared tunnel info tradenest-webhook`).
- Public hostname resolves: `dig +short tradenest-webhook.<your-domain>` returns Cloudflare IPs.
- Public health probe matches local: `curl -fsS https://tradenest-webhook.<your-domain>/api/status` returns the same body as the local call.
- Webhook smoke test (with a fresh ISO timestamp) returns 2xx and lands a row in `signals` + `runs`.
- Wrong path token returns `HTTP 401 invalid_path_token`.
- Wrong `auth_token` returns `HTTP 401 invalid_payload_auth_token`.
- Stale `signal_generated_at` returns `HTTP 422 stale_tradingview_signal`.
- Duplicate of an accepted signal returns `HTTP 409 duplicate_signal`.
- No public hostname exists for the dashboard: `dig +short tradenest-dashboard.<your-domain>` is empty.
- Kill switch exercised: `POST /api/system/kill` blocks the next signal with `risk_decision = blocked`; `POST /api/system/unkill` clears it.
- `.env` shows `TRADENEST_MODE=paper` and `TRADENEST_KILL_SWITCH=false`.
- `git check-ignore .env` prints `.env` (i.e. it stays out of the repo).

## Token Rotation (TradingView path token + auth token)

- Generate two new high-entropy tokens (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`).
- Update `TRADINGVIEW_PATH_TOKEN` and `TRADINGVIEW_AUTH_TOKEN` in `~/tradenest-runtime/.env`.
- Reload backend: `launchctl unload` then `launchctl load` `~/Library/LaunchAgents/tradenest-backend.plist`.
- Update the TradingView alert(s): webhook URL path token segment and `auth_token` value in the alert message.
- Send one webhook smoke test (curl) and confirm 2xx.
- Hit the webhook with the **old** path token and confirm `HTTP 401 invalid_path_token`.
- Confirm the new tokens never made it into the repo: `git status` shows no changes under tracked files.
