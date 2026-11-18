# Signal Bot

A self-hosted Signal messaging bot with a web dashboard. Create scheduled jobs, trigger actions on incoming messages, or fire jobs via webhooks — all managed through a Django-based UI.

## Requirements

- Python 3.11+
- [signal-cli](https://github.com/AsamK/signal-cli) 0.14+
- Java 21+ (for signal-cli)

## Setup

```bash
# Install dependencies
uv sync

# Run migrations
uv run python manage.py migrate

# Start everything (web server + scheduler + message listener)
uv run python main.py
```

Dashboard at `http://localhost:8000`.

## Linking a Signal Account

1. Go to **Account** in the dashboard
2. Click **Start Linking** — a QR code appears
3. On your phone: Signal Settings > Linked Devices > Link New Device > scan the QR code
4. The dashboard updates when linking completes

Or via CLI:
```bash
signal-cli link -n "my-bot"
# Scan the QR URI with Signal, then:
signal-cli listAccounts
```

## Jobs

### Simple Jobs
Send a static message to one or more chats. Configure entirely in the dashboard — no code needed.

### Script Jobs
Run a Python script from the `scripts/` directory. Every script must define a `run(ctx)` entry point:

```python
def run(ctx):
    ctx.log.info("Running my script")
    for chat in ctx.target_chats:
        ctx.signal.send_to_chat(chat, "Hello!")
```

**`ctx` attributes:**
| Attribute | Description |
|---|---|
| `ctx.signal` | `SignalClient` — send messages, list groups/contacts |
| `ctx.target_chats` | List of `Chat` objects assigned to this job |
| `ctx.config` | `dict` from the job's JSON config field |
| `ctx.trigger_context` | Info about what triggered the run (sender, message, payload) |
| `ctx.log` | Logger — output is captured in the execution log |

**Utility helpers** (importable in scripts):
```python
from core.utils import send_to_all, format_table
```

## Triggers

Each job can have multiple triggers:

### Cron (time-based)
Uses standard cron expressions. The scheduler checks every 30 seconds.

| Expression | Meaning |
|---|---|
| `* * * * *` | Every minute |
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 1 * *` | First day of every month at midnight |
| `30 8 * * 1` | Every Monday at 8:30 AM |

**Format:** `minute hour day-of-month month day-of-week`

| Field | Values |
|---|---|
| Minute | 0–59 |
| Hour | 0–23 |
| Day of month | 1–31 |
| Month | 1–12 |
| Day of week | 0–7 (0 and 7 = Sunday) |

**Special characters:**
- `*` — any value
- `,` — list (`1,3,5`)
- `-` — range (`1-5`)
- `/` — step (`*/10` = every 10)

### Message (incoming message pattern)
Trigger when a received message matches a regex pattern. Optionally scope to specific chats.

### Webhook (HTTP POST)
Each webhook trigger gets a unique token. Fire it with:
```bash
curl -X POST http://your-server:8000/webhook/<token>/ \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```
The payload is available in `ctx.trigger_context["payload"]`.

## Registering a number (e.g. a landline) instead of linking

Dashboard → **Account** → *register a phone number* (`/register/`). The wizard walks through
signal-cli's flow: captcha (from signalcaptchas.org) → request SMS (required by Signal even for
landlines) → after ~1 min request a voice call → enter the 6-digit code, optionally set a
profile name and a registration-lock PIN. While a registration is in progress the listener
doesn't start signal-cli for the account. Signal Desktop can then be linked to the bot's
account via *Linked devices* on the same page.

## Reminder API (for signal-bot-reminder-generator)

Enabled when `REMINDER_API_TOKEN` is set; `Authorization: Bearer <token>`.

| Endpoint | |
|---|---|
| `GET /api/v1/status/` | account + whether signal-cli runs |
| `GET /api/v1/groups/`, `POST /api/v1/groups/sync/` | Signal groups known to the bot |
| `GET /api/v1/groups/members/?id=<group id>` | members (uuid, number, name) |
| `POST /api/v1/preview/` | `{spec, from?, days?}` → messages that would be sent (dry run) |
| `GET /api/v1/reminders/` | managed reminder jobs |
| `PUT/GET/DELETE /api/v1/reminders/<id>/` | upsert `{group_id, spec, enabled, name?}` |
| `POST /api/v1/reminders/<id>/run/` | send now (next occurrence) |
| `GET /api/v1/reminders/<id>/executions/` | run logs |

Specs are documented in `core/reminders.py` and executed by `scripts/reminder_runner.py`.

## Configuration via environment

`SECRET_KEY`, `DEBUG` (default 1), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DB_PATH`, `STATIC_ROOT`,
`BIND_ADDRESS` (default `0.0.0.0:8000`), `DASHBOARD_REQUIRE_LOGIN` (default 0; 1 = Django login
for the dashboard), `SIGNAL_CLI_PATH`, `SIGNAL_CLI_DATA_DIR`, `REMINDER_API_TOKEN`,
`REMINDER_DEFAULT_TZ` (default Europe/Berlin). Defaults keep the previous behaviour.
`HTTPS` (default 0; 1 = running behind a TLS proxy: trust `X-Forwarded-Proto`, secure cookies).

On signal-bot.schollheim.net the dashboard is served by nginx at
`https://dashboard-signal-bot.schollheim.net` (intranet only) with the Schollheim wildcard
certificate (`/etc/ssl/certs/schollheim_net_bundle.cer`, key in `/etc/ssl/private/`), copied from
the other Schollheim servers. **It expires 2027-01-31 and must be renewed there by hand** (then
`systemctl reload nginx`).

## Systemd Service

```ini
[Unit]
Description=Signal Bot
After=network.target

[Service]
Type=forking
User=your-user
WorkingDirectory=/path/to/signal-bot
ExecStart=/usr/bin/tmux new-session -d -s signal-bot uv run python main.py
ExecStop=/usr/bin/tmux kill-session -t signal-bot
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Attach to the session: `tmux attach -t signal-bot`

## Project Structure

```
signal-bot/
├── main.py              # Process orchestrator
├── scripts/             # User job scripts (run(ctx) entry point)
├── core/                # Engine: models, signal-cli client, scheduler, listener
├── dashboard/           # Web UI (Django templates + HTMX)
└── webhook/             # Webhook trigger endpoint
```
