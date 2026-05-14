# Cloudflare Tunnel and TradingView Setup

This guide covers the public exposure layer for TradeNest. Read it
before pointing real TradingView alerts at the backend.

## Goal and Non-goals

**Goal.** Make exactly one URL reachable from the public internet:

```text
POST https://tradenest-webhook.<your-domain>/webhook/tradingview/<TRADINGVIEW_PATH_TOKEN>
```

That URL is the only path TradingView will hit. Everything else stays
local.

**Non-goals for this commit.**

- The dashboard at `http://127.0.0.1:3000` stays private (Tailscale-only
  or LAN-only). Never expose it via the public tunnel hostname.
- No live Bybit execution, no websocket feed, no Claude critic, no
  LangGraph/LangSmith wiring. Public exposure is paper-trade only until
  promotion criteria are met.
- No Cloudflare WAF transformations that modify path, query, headers,
  or body — they will break the webhook contract.
- No Cloudflare Access service-token requirement on this hostname.
  TradingView's webhook sender cannot attach custom auth headers, so
  Access service tokens would silently lock out real alerts.

## Webhook Contract (the truth the runbook relies on)

The FastAPI webhook route lives at:

```text
POST /webhook/tradingview/{secret_path_token}
```

It enforces, in order:

1. URL path token must equal `TRADINGVIEW_PATH_TOKEN` from `.env`.
   Mismatch → `HTTP 401` with `reason: invalid_path_token`.
2. JSON body must validate against the webhook payload schema.
   Failure → `HTTP 422` with `reason: invalid_payload_schema`.
3. JSON body field `auth_token` must equal `TRADINGVIEW_AUTH_TOKEN`.
   Mismatch → `HTTP 401` with `reason: invalid_payload_auth_token`.
4. If `source == "TradingView"`, the `signal_generated_at` timestamp
   must be within `TRADINGVIEW_MAX_STALE_SECONDS` of now. Replay and
   Manual sources bypass this stale check.
   Stale → `HTTP 422` with `reason: stale_tradingview_signal`.
5. Successful inserts compute a dedupe key. Repeats → `HTTP 409` with
   `reason: duplicate_signal`.
6. Accepted signals advance through the deterministic pipeline (signal
   engine → market features → risk gate → paper broker).

Two reasons the runbook insists on path token AND payload token:

- The path token alone is observable in TLS-terminated logs (Cloudflare
  Tunnel proxies are inside the TLS path). The payload token gives a
  second factor inside the encrypted body.
- Token rotation can be done in two halves (rotate path token first,
  then payload token, or vice versa) without an outage.

## Public Hostname Pattern

Use one subdomain that is dedicated to TradeNest:

```text
tradenest-webhook.<your-domain>
```

The full webhook URL is:

```text
https://tradenest-webhook.<your-domain>/webhook/tradingview/<TRADINGVIEW_PATH_TOKEN>
```

Rules:

- Always use the **path token**, never a query string. Query strings
  end up in access logs more aggressively than path segments and break
  the existing contract.
- Do not stack additional path segments. The route is exact.
- Do not put the auth token in the URL. It belongs in the JSON body.

## Path A — Cloudflare Dashboard–Managed Tunnel (recommended for v1)

This is the click-through path. Cloudflare stores the tunnel config and
credentials for you; you only run `cloudflared` locally as a connector.

1. Install `cloudflared` on the Mac mini:
   ```bash
   brew install cloudflared
   cloudflared --version
   ```
2. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels**.
3. **Create a tunnel** named `tradenest-webhook`.
4. Cloudflare gives you an `install` command (a long token-based
   invocation). Run it on the Mac mini. This installs and starts
   `cloudflared` as a service that authenticates to your tunnel.
5. Under that tunnel, add a **Public Hostname** (also called a
   Published Application) with:
   - **Subdomain:** `tradenest-webhook`
   - **Domain:** `<your-domain>` (must already be on Cloudflare)
   - **Type:** `HTTP`
   - **URL:** `http://127.0.0.1:8000`
6. Save. Wait until the tunnel connector shows status **Healthy**.
7. (Optional, paranoid) Add a second public hostname only if you
   intend to expose another local service — TradeNest only needs the
   one. Do NOT add a hostname for `127.0.0.1:3000`.

Verification:

```bash
curl -fsS https://tradenest-webhook.<your-domain>/api/status
```

Note: `/api/status` becoming publicly reachable is a side effect of
exposing the whole backend through the tunnel. That is acceptable for
v1 because the public surface area is still just one host, and the
status endpoint returns no secrets. Production discipline: treat the
webhook URL as the only intended public path and don't link
`/api/status` anywhere external.

## Path B — Locally Managed Tunnel

This is the YAML-config path. Tunnel definition and credentials live
in `~/.cloudflared/` on the Mac mini. Use this if you want config in
version control (excluding the credentials JSON) or if you don't want
the Cloudflare-side install command.

1. Install `cloudflared`:
   ```bash
   brew install cloudflared
   ```
2. Authenticate:
   ```bash
   cloudflared tunnel login
   ```
   This opens a browser, has you pick the zone, and drops a
   `cert.pem` in `~/.cloudflared/`.
3. Create the tunnel:
   ```bash
   cloudflared tunnel create tradenest-webhook
   ```
   This writes `~/.cloudflared/<tunnel-id>.json` (the credentials).
4. Route DNS:
   ```bash
   cloudflared tunnel route dns tradenest-webhook tradenest-webhook.<your-domain>
   ```
5. Create `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: tradenest-webhook
   credentials-file: /Users/bharatmacmini/.cloudflared/<tunnel-id>.json

   ingress:
     - hostname: tradenest-webhook.<your-domain>
       service: http://127.0.0.1:8000
     - service: http_status:404
   ```
   The trailing catch-all `http_status:404` is required by
   `cloudflared` — it must be the last rule.
6. Run the tunnel in the foreground first to confirm it works:
   ```bash
   cloudflared tunnel run tradenest-webhook
   ```
   Look for connector lines like
   `Registered tunnel connection connIndex=0 ... location=...`.
7. Once happy, run it under launchd via the optional templates in
   `ops/scripts/run-cloudflared.sh` and
   `ops/launchd/tradenest-cloudflared.plist`. Those templates are
   provided but **not auto-loaded** — copy and `launchctl load`
   manually after you've validated the foreground run.

Cloudflare's docs describe the locally-managed flow as: install
`cloudflared`, authenticate, create the tunnel, write the config,
route traffic, run the tunnel, then check the tunnel.

## TradingView Alert Setup

1. Open the chart on `<symbol>` at the timeframe you want to trade.
2. Add the indicator or strategy whose signals you want to forward.
3. Open the **Alerts** panel (clock icon) → **Create Alert**.
4. **Condition:** select the indicator/strategy condition. For
   strategies, choose `Order fills only` if you only want entries and
   exits, or `Any alert() function call` if your Pine script emits its
   own granular alerts.
5. **Options → Webhook URL:** check the box and paste:
   ```text
   https://tradenest-webhook.<your-domain>/webhook/tradingview/<TRADINGVIEW_PATH_TOKEN>
   ```
6. **Message:** paste the JSON template below (next section).
7. **Alert actions:** leave Email/Notification disabled unless you want
   them — the webhook is the source of truth.
8. **Expiration:** set to `Open-ended` so the alert keeps firing.
9. Click **Create**.
10. Trigger a test condition (for example, an indicator that crosses
    immediately, or use TradingView's "Test webhook" via firing a
    one-off `alert()` call). Confirm it arrives:
    - Backend: `curl http://127.0.0.1:8000/api/journal | head`
    - Dashboard Trade Journal at `http://127.0.0.1:3000`
    - SQLite: `signals`, `runs`, `audit_logs` tables
    - launchd logs: `~/tradenest-runtime/logs/backend.out.log`

TradingView's docs confirm that webhook alerts send an `HTTP POST` to
the configured URL with the alert message as the request body, and
that placeholders like `{{ticker}}`, `{{close}}`, `{{interval}}`,
`{{time}}`, and `{{plot_0}}` are substituted at fire time.

## TradingView Alert JSON Template

Paste this into the alert's **Message** field:

```json
{
  "source": "TradingView",
  "auth_token": "<TRADINGVIEW_AUTH_TOKEN>",
  "strategy_id": "cvd_rubric_v1",
  "symbol": "{{ticker}}",
  "side": "{{strategy.order.action}}",
  "signal_type": "ENTRY",
  "timeframe": "{{interval}}",
  "bar_id": "{{ticker}}-{{interval}}-{{time}}",
  "price": {{close}},
  "signal_generated_at": "{{time}}",
  "atr": "{{plot_0}}"
}
```

Adapt notes — read these before you go live:

- **`auth_token`** must be a literal string equal to your `.env`
  `TRADINGVIEW_AUTH_TOKEN`. TradingView will not template it; you
  paste the real value here. Treat this template as a secret once
  filled in.
- **`side`** uses `{{strategy.order.action}}` which TradingView emits
  as lowercase `buy` or `sell`. The backend's `side` field is the
  literal enum `buy | sell | long | short` (lowercase), so this maps
  cleanly. If you switch to an indicator-based template that emits
  `BUY`/`SELL` from Pine code, normalize to lowercase before sending.
- **`price`** is unquoted on purpose. `{{close}}` substitutes as a
  number; quoting it would break JSON. If your Pine script ever emits
  a non-numeric value here, TradingView will produce invalid JSON and
  the alert won't fire.
- **`atr`** is the trickier placeholder. `{{plot_0}}` is the value of
  the indicator's first plot at fire time — only correct if the
  indicator on the alert *is* the ATR (or if the strategy's first plot
  is ATR). If your strategy doesn't expose ATR as plot 0, either:
  - update the Pine script to add an `atr_plot` plot in slot 0, or
  - drop the `atr` field from the JSON and let the backend's
    market-features stage compute ATR from the Bybit price feed.
- **`signal_generated_at`** must be `{{time}}`. The backend's stale
  check (default 300 s) compares this against server `now()`. If your
  Pine alert uses `alert()` calls deep in the script, `{{time}}` is
  the bar time — be aware of bar-close vs. real-time semantics.
- The JSON template should validate locally before pasting:
  `python -m json.tool < template.json` (replace placeholders with
  dummy values first).

## Test Commands

### 1. Local backend health

```bash
curl -fsS http://127.0.0.1:8000/api/status
```

Expect a JSON body with `"backend_health":"ok"`.

### 2. Public tunnel health

```bash
curl -fsS https://tradenest-webhook.<your-domain>/api/status
```

Expect the same body. If this 502s or hangs, the tunnel connector is
not healthy. If it returns Cloudflare's HTML error page, DNS routed to
Cloudflare but the connector is not running locally.

### 3. Webhook smoke test (paper-mode safe)

```bash
curl -sS -X POST "https://tradenest-webhook.<your-domain>/webhook/tradingview/<TRADINGVIEW_PATH_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "TradingView",
    "auth_token": "<TRADINGVIEW_AUTH_TOKEN>",
    "strategy_id": "cvd_rubric_v1",
    "symbol": "BTCUSDT",
    "side": "buy",
    "signal_type": "ENTRY",
    "timeframe": "15m",
    "bar_id": "BTCUSDT-15m-test-001",
    "price": 65000,
    "signal_generated_at": "<CURRENT_ISO_TIMESTAMP>"
  }'
```

Replace `<CURRENT_ISO_TIMESTAMP>` with a UTC timestamp inside the
stale window, e.g. via:

```bash
python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())"
```

A stale timestamp will be rejected with `HTTP 422 stale_tradingview_signal`.

### 4. External-network test from your phone

Mac mini, TradingView, and your phone are all on the same Cloudflare
edge, but the most realistic test is to exit the LAN:

- Disable Wi-Fi on your phone, switch to mobile data.
- Use an app like *HTTPBot*, *RESTed*, or *Shortcuts* with a
  `Get Contents of URL` action to POST the JSON above.
- Confirm a 2xx is returned and the row appears in the backend journal.

If you can't easily test from a phone, tether the Mac through your
phone's mobile data and re-run the curl — same effect.

## Deployment-Day Checklist (paper-mode only)

1. TradeNest backend running on `127.0.0.1:8000` (`launchctl list | grep tradenest`).
2. `~/tradenest-runtime/ops/scripts/healthcheck.sh` exits 0.
3. Cloudflare tunnel connector shows Healthy in dashboard or
   foreground logs.
4. `dig +short tradenest-webhook.<your-domain>` returns Cloudflare IPs.
5. Public health check (`curl … /api/status`) returns the same JSON
   as the local backend.
6. Webhook curl smoke test returns a 2xx and lands in `/api/journal`.
7. Repeat the smoke test with a wrong path token — expect `HTTP 401`.
8. Repeat with a wrong `auth_token` — expect `HTTP 401`.
9. Repeat with a stale `signal_generated_at` (set it 1 h in the past)
   — expect `HTTP 422 stale_tradingview_signal`.
10. Public hostname for the dashboard does **not** exist
    (`dig +short tradenest-dashboard.<your-domain>` should be empty).
11. Create the first real TradingView alert with the JSON template.
12. Trigger it once on a safe condition. Confirm a row in `signals`
    and a paired row in `runs`.
13. Trigger the same condition again. Confirm the second hit is
    rejected `HTTP 409 duplicate_signal`.
14. `curl -X POST http://127.0.0.1:8000/api/system/kill` — confirm
    next alert is blocked with `risk_decision = blocked`.
    `curl -X POST http://127.0.0.1:8000/api/system/unkill` to clear.
15. `TRADENEST_MODE` stays `paper` in `.env`. Live execution is not
    enabled by this commit.

## Troubleshooting

| Symptom | First place to look |
| --- | --- |
| `HTTP 401 invalid_path_token` | URL path token doesn't match `TRADINGVIEW_PATH_TOKEN` in `.env`. Re-check the path segment (no trailing slash, no extra path). |
| `HTTP 401 invalid_payload_auth_token` | JSON `auth_token` field doesn't match `TRADINGVIEW_AUTH_TOKEN`. Inspect via `tail -f ~/tradenest-runtime/logs/backend.out.log` while TradingView fires. |
| `HTTP 422 stale_tradingview_signal` | `signal_generated_at` is older than `TRADINGVIEW_MAX_STALE_SECONDS`. Check Mac mini clock (`sudo sntp -sS time.apple.com`) and TradingView bar-time alignment. |
| `HTTP 422 invalid_payload_schema` | JSON didn't validate. Common causes: `price` quoted as a string, `side` capitalized, missing required field, TradingView placeholder unresolved (e.g. `{{plot_0}}` literal text). |
| TradingView alert fires but no journal row | If the response code is 2xx, the row is there — query SQLite directly: `sqlite3 ~/tradenest-runtime/data/tradenest.sqlite3 "SELECT * FROM signals ORDER BY id DESC LIMIT 5;"`. If non-2xx, look in `audit_logs` for the rejection reason. |
| Tunnel down (Cloudflare returns 5xx) | `cloudflared` not running. `launchctl list \| grep cloudflared` or check the Cloudflare dashboard connector status. Restart per Path A or Path B. |
| Backend down (Cloudflare returns 502) | Tunnel is up but `127.0.0.1:8000` isn't responding. `curl http://127.0.0.1:8000/api/status` locally; check `~/tradenest-runtime/logs/backend.err.log`. |
| Port 8000 occupied | `lsof -i :8000` to see what's bound. If a stale uvicorn is left over: `launchctl unload ~/Library/LaunchAgents/tradenest-backend.plist && launchctl load …` |
| Cloudflare route points to wrong service URL | Dashboard tunnel config Path A: edit Public Hostname → URL. Path B: edit `~/.cloudflared/config.yml` ingress block. |
| Dashboard accidentally exposed | Check Cloudflare dashboard → Tunnels → Public Hostnames. If a hostname routes to `127.0.0.1:3000`, delete it immediately. The intended config has exactly one hostname routing to `127.0.0.1:8000`. |
| Replay works but TradingView does not | Replay bypasses the stale check; TradingView doesn't. Run the curl smoke test with a *fresh* timestamp from your laptop. If that works but TradingView still fails, the TradingView JSON is malformed — see "invalid_payload_schema". |
| Placeholders producing unexpected `side` values | Strategy is emitting non-`buy`/`sell` text. Inspect the raw POST body via `audit_logs` and fix the Pine script. |

## Token Rotation Procedure

Rotate when: leak suspected, end of paper-trial window, or as a
quarterly hygiene step.

1. Generate two new high-entropy strings, one for path, one for
   payload. Suggested length: 32+ chars, URL-safe:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Edit `~/tradenest-runtime/.env` and replace
   `TRADINGVIEW_PATH_TOKEN` and `TRADINGVIEW_AUTH_TOKEN`.
3. Reload backend so it picks up the new env:
   ```bash
   launchctl unload ~/Library/LaunchAgents/tradenest-backend.plist
   launchctl load   ~/Library/LaunchAgents/tradenest-backend.plist
   ```
4. Update the TradingView alert(s):
   - Edit each alert → Options → Webhook URL → update the path token
     segment.
   - Edit each alert → Message → update `auth_token` value.
5. Send one test alert (use the curl smoke test from this doc).
6. Confirm the **old** path token now returns `HTTP 401`.
7. Never commit either token. They live in `.env` (gitignored) and in
   the TradingView alert UI only.
8. Optional: rotate the two tokens at different times so the change
   window for any single token is shorter than the rotation interval.

## Security Checklist (read every time before a public deploy)

- Public hostname routes only to `127.0.0.1:8000`. No dashboard
  hostname.
- No Cloudflare Access service-token policy on the webhook hostname.
  TradingView cannot send the required `CF-Access-Client-Id` /
  `CF-Access-Client-Secret` headers, so the alerts would be blocked.
- Bybit API keys never enter TradingView. Bybit talks only to the
  backend's price-feed module, which uses public endpoints.
- Telegram bot token never enters TradingView.
- `.env` never enters the repo. Verify with `git check-ignore .env`.
- Tokens travel in the URL path segment and JSON body — never as
  query string parameters.
- Rotate tokens if they were ever pasted into Slack, screenshots, or a
  shared note.
- No Cloudflare Rules that rewrite path, query, headers, or body —
  they will break the path token, the JSON body, or both.
- WAF rules: leave off for v1. Add an IP-allowlist rule for
  TradingView's published IP ranges *after* you have 100+ real alerts
  observed in production, since the published ranges change.
- Tunnel runs as the user (`bharatmacmini`), not root. Confirm:
  `ps -ef | grep cloudflared`.

## Promotion Criteria Before Anything Beyond v1

Do not move past this v1 public exposure until all of:

- 100+ real TradingView alerts have been observed and processed
  without manual intervention.
- Zero unexplained `HTTP 5xx` from the public hostname over 7
  consecutive days.
- Backup script has run weekly with confirmed restoration of at least
  one backup into a scratch SQLite file.
- Kill switch has been exercised at least once against a live
  TradingView alert and observed to block correctly.
- `TRADENEST_MODE` has stayed `paper` the entire time.

Live execution, websocket feeds, LLM critique, and dashboard exposure
are all gated behind these criteria.
