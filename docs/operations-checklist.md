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
