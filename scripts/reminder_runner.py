"""Generic runner for declarative reminder specs (see core/reminders.py).

Jobs using this script are created via the API (/api/v1/reminders/...) by
signal-bot-reminder-generator. The job's config_json is the spec. The API schedules it
at send_time for both UTC offsets of the spec's timezone (e.g. "0 7,8 * * *" for 09:00
Berlin); the runner checks the local time itself and remembers the last day it sent, so
the extra run is a no-op and DST is handled.

Config extras (not part of the spec):
  "external_id": used as the state key (set by the API)
  "force": true  -> ignore send_time / already-sent state (used by "run now")
"""

from core import reminders
from core.utils import load, resolve_group_members, send_with_mentions, store


def run(ctx):
    spec = reminders.validate(ctx.config)
    key = ctx.config.get("external_id") or spec["title"]
    force = bool(ctx.trigger_context.get("payload", {}).get("force")) or bool(ctx.config.get("force"))

    now = reminders.local_now(spec)
    today = now.date()
    state = load("reminder", key, {}) or {}
    if not force:
        if not reminders.send_time_reached(spec, now):
            return
        if state.get("last_sent") == today.isoformat():
            return

    due = reminders.reminders_due(spec, today)
    if force and not due:
        # "Run now" with nothing due today: send the next upcoming reminder as a test.
        nxt = reminders.upcoming(spec, today, days=400)
        if nxt:
            _, occ, people = nxt[0]
            due = [(occ, people)]
            ctx.log.info("Nothing due today; test-sending next occurrence %s", occ)

    if not due:
        return

    for chat in ctx.target_chats:
        members = resolve_group_members(ctx.signal, chat) if chat.chat_type == "group" else None
        for occ, people in due:
            text, specs, warnings = reminders.render(spec, occ, people, today, members)
            for w in warnings:
                ctx.log.warning(w)
            if specs:
                send_with_mentions(ctx.signal, chat, text, specs)
            else:
                ctx.signal.send_to_chat(chat, text)
            ctx.log.info("Sent to %s: %s", chat, text)

    if not force:
        store("reminder", key, {**state, "last_sent": today.isoformat()})
