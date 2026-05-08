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
