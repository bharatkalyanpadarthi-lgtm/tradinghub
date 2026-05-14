# TradeNest Operations Checklist

## Daily Check

- Run `ops/scripts/healthcheck.sh`.
- Open Mission Control and confirm backend health is `ok`.
- Check `/status` in Telegram if enabled.
- Confirm kill switch is clear unless intentionally enabled.
- Review today signal count, blocked count, open positions, and paper P&L.
- Confirm no unexpected duplicate bursts in replay or webhook runs.

## Weekly Check

- Run `ops/scripts/backup_sqlite.sh`.
- Confirm a fresh backup exists in `./backups/`.
- Run `ops/scripts/rotate_logs.sh`.
- Run backend tests: `.venv/bin/python -m pytest -q`.
- Build dashboard: `cd dashboard && npm run build`.
- Review Trade Journal for closed positions and P&L sanity.

## Before Reboot

- Confirm latest backup exists.
- Confirm no critical paper validation run is in progress.
- Note current kill switch state.
- Unload launchd services if doing maintenance:
  - `launchctl unload ~/Library/LaunchAgents/tradenest-dashboard.plist`
  - `launchctl unload ~/Library/LaunchAgents/tradenest-backend.plist`

## After Reboot

- Confirm launchd services are loaded or start them manually.
- Run `ops/scripts/healthcheck.sh`.
- Open dashboard at `http://127.0.0.1:3000`.
- Call `curl -fsS http://127.0.0.1:8000/api/status`.
- Send Telegram `/status` if Telegram is enabled.
- Run one replay dry-run using `tradenest/replay/sample_signals.csv`.
