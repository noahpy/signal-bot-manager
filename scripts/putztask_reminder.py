import json
from datetime import date, timedelta
from pathlib import Path

from core.utils import (
    get_group_members,
    get_name,
    mention,
    send_with_mentions,
)

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

TASKS_FILE = Path(__file__).parent / "putztasks.json"


def _parse_date(date_str, year):
    """Returns (month, day) for DD.MM or (month, None) for month names."""
    low = date_str.strip().lower()
    if low in GERMAN_MONTHS:
        return GERMAN_MONTHS[low], None
    parts = date_str.strip().split(".")
    if len(parts) == 2:
        return int(parts[1]), int(parts[0])
    return None, None


def _match_member(name, members, log=None):
    name_lower = name.lower()
    best = None
    best_score = -1
    for m in members:
        full = (get_name(m["number"]) or "").lower()
        if not full:
            continue
        if name_lower == full:
            if log:
                log.info("  [debug] '%s' -> exact match: %s (%s)", name, m["number"], get_name(m["number"]))
            return m
        if name_lower in full or full in name_lower:
            score = len(name_lower)
            if score > best_score:
                best_score = score
                best = m
    if log and best:
        log.info("  [debug] '%s' -> best match: %s (%s)", name, best["number"], get_name(best["number"]))
    elif log:
        log.info("  [debug] '%s' -> NO MATCH FOUND", name)
    return best


def _build_mention_message(members_to_mention, prefix):
    texts_and_builders = []
    for m in members_to_mention:
        display = get_name(m["number"]) or m["number"]
        text, builder = mention(m["number"], display)
        texts_and_builders.append((text, builder))

    names_part = ", ".join(t for t, _ in texts_and_builders)
    full_msg = prefix + names_part
    specs = []
    for text, builder in texts_and_builders:
        idx = full_msg.index(text)
        specs.append(builder(idx))
    return full_msg, specs


def _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, members, task_date, days_until, debug_log=None):
    if assignee_name:
        matched = _match_member(assignee_name, members, log=debug_log)
        if matched:
            display = get_name(matched["number"]) or assignee_name
            text, builder = mention(matched["number"], display)
            if days_until == 0:
                msg = f"Erinnerung: {task_name} ist heute dran! Zuständig: {text}"
            else:
                msg = f"Erinnerung: {task_name} ist am {task_date.strftime('%d.%m.')} dran (in {days_until} Tagen). Zuständig: {text}"
            send_with_mentions(ctx.signal, chat, msg, [builder(msg.index(text))])
        else:
            if days_until == 0:
                msg = f"Erinnerung: {task_name} ist heute dran! Zuständig: {assignee_name}"
            else:
                msg = f"Erinnerung: {task_name} ist am {task_date.strftime('%d.%m.')} dran (in {days_until} Tagen). Zuständig: {assignee_name}"
            ctx.signal.send_to_chat(chat, msg)
    else:
        members_to_mention = [_match_member(a, members, log=debug_log) for a in assignee_names]
        members_to_mention = [m for m in members_to_mention if m]
        if days_until == 0:
            prefix = f"Erinnerung: {task_name} ist heute dran! Zuständig: "
        else:
            prefix = f"Erinnerung: {task_name} ist am {task_date.strftime('%d.%m.')} dran (in {days_until} Tagen). Zuständig: "
        if members_to_mention:
            msg, specs = _build_mention_message(members_to_mention, prefix)
            send_with_mentions(ctx.signal, chat, msg, specs)
        else:
            ctx.signal.send_to_chat(chat, prefix + ", ".join(assignee_names))


def run(ctx):
    ctx.log.info("=== Putztask Reminder ===")
    debug = ctx.config.get("debug", False)
    debug_log = ctx.log if debug else None

    chat = ctx.target_chats[0]
    members = get_group_members(ctx.signal, chat)
    ctx.log.info("Group '%s' has %d members", chat.name, len(members))

    with open(TASKS_FILE) as f:
        data = json.load(f)

    if debug:
        all_assignees = set()
        for task in data["tasks"]:
            all_assignees.update(task["assignees"])
        ctx.log.info("[debug] === Assignee matching report ===")
        for name in sorted(all_assignees):
            _match_member(name, members, log=ctx.log)

    today = date.today()
    ctx.log.info("Today: %s", today.isoformat())
    reminders_sent = 0

    for task in data["tasks"]:
        task_name = task["task"]
        assignee_names = task["assignees"]
        schedule = task.get("schedule", [])
        is_tafel = task_name.lower() == "tafel"

        if not schedule:
            if today.day != 1:
                continue
            ctx.log.info("Task '%s' has no schedule -> monthly reminder on 1st", task_name)
            _send_reminder(ctx, chat, task_name, None, assignee_names, members, today, 0, debug_log)
            reminders_sent += 1
            continue

        for entry in schedule:
            month, day = _parse_date(entry["date"], today.year)
            if month is None:
                continue

            assignee_name = entry.get("assignee")

            if day is not None:
                try:
                    task_date = date(today.year, month, day)
                except ValueError:
                    continue

                if is_tafel:
                    remind_date = task_date
                else:
                    remind_date = task_date - timedelta(days=4)

                if today != remind_date:
                    continue

                days_until = (task_date - today).days
                _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, members, task_date, days_until, debug_log)
                ctx.log.info("Sent reminder for '%s' (due %s, assignee=%s)", task_name, task_date, assignee_name or "all")
                reminders_sent += 1
            else:
                if today != date(today.year, month, 15):
                    continue
                _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, members, today, 0, debug_log)
                ctx.log.info("Sent monthly reminder for '%s' (month=%d, assignee=%s)", task_name, month, assignee_name or "all")
                reminders_sent += 1

    ctx.log.info("Done. Sent %d reminder(s) today.", reminders_sent)
