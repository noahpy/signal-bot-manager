import json
from datetime import date, timedelta
from pathlib import Path

from core.models import Chat
from core.utils import (
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


def _part_matches(query_part, full_part):
    """Check if query_part matches full_part meaningfully.
    Strips trailing dots (abbreviations like 'Sch.' or 'S.') before matching.
    Requires at least 2 chars overlap to avoid spurious single-letter matches.
    """
    qp = query_part.rstrip(".")
    fp = full_part.rstrip(".")
    if len(qp) < 2 or len(fp) < 2:
        return False
    return qp.startswith(fp) or fp.startswith(qp)


def _match_contact(name, contacts, log=None):
    name_lower = name.lower()
    name_parts = name_lower.split()
    best = None
    best_score = -1
    for c in contacts:
        full = c.name.lower()
        if not full or len(full) < 2:
            continue
        if name_lower == full:
            if log:
                log.info("  [debug] '%s' -> exact match: %s (%s)", name, c.identifier, c.name)
            return c
        full_parts = full.split()
        # Every query part must match some full name part
        matched_parts = 0
        total_overlap = 0
        for np in name_parts:
            for fp in full_parts:
                if _part_matches(np, fp):
                    matched_parts += 1
                    total_overlap += min(len(np.rstrip(".")), len(fp.rstrip(".")))
                    break
        if matched_parts == len(name_parts) and matched_parts > 0:
            score = total_overlap * 10 + matched_parts
            if score > best_score:
                best_score = score
                best = c
    if log and best:
        log.info("  [debug] '%s' -> best match: %s (%s)", name, best.identifier, best.name)
    elif log:
        log.info("  [debug] '%s' -> NO MATCH FOUND", name)
    return best


def _is_phone(identifier):
    return identifier.startswith("+")


def _build_mention_message(contacts_to_mention, prefix):
    texts_and_builders = []
    plain_names = []
    for c in contacts_to_mention:
        display = c.name or c.identifier
        if _is_phone(c.identifier):
            text, builder = mention(c.identifier, display)
            texts_and_builders.append((text, builder))
        else:
            plain_names.append(display)

    all_parts = [t for t, _ in texts_and_builders] + plain_names
    names_part = ", ".join(all_parts)
    full_msg = prefix + names_part
    specs = []
    for text, builder in texts_and_builders:
        idx = full_msg.index(text)
        specs.append(builder(idx))
    return full_msg, specs


def _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, contacts, task_date, days_until, debug_log=None):
    if days_until == 0:
        prefix = f"Erinnerung: {task_name} ist heute dran! Zuständig: "
    else:
        prefix = f"Erinnerung: {task_name} ist am {task_date.strftime('%d.%m.')} dran (in {days_until} Tagen). Zuständig: "

    if assignee_name:
        matched = _match_contact(assignee_name, contacts, log=debug_log)
        if matched and _is_phone(matched.identifier):
            display = matched.name or assignee_name
            text, builder = mention(matched.identifier, display)
            msg = prefix + text
            send_with_mentions(ctx.signal, chat, msg, [builder(msg.index(text))])
        else:
            display = matched.name if matched else assignee_name
            ctx.signal.send_to_chat(chat, prefix + display)
    else:
        matched_contacts = [_match_contact(a, contacts, log=debug_log) for a in assignee_names]
        matched_contacts = [c for c in matched_contacts if c]
        if matched_contacts:
            msg, specs = _build_mention_message(matched_contacts, prefix)
            if specs:
                send_with_mentions(ctx.signal, chat, msg, specs)
            else:
                ctx.signal.send_to_chat(chat, msg)
        else:
            ctx.signal.send_to_chat(chat, prefix + ", ".join(assignee_names))


def run(ctx):
    ctx.log.info("=== Putztask Reminder ===")
    debug = ctx.config.get("debug", False)
    debug_log = ctx.log if debug else None

    chat = ctx.target_chats[0]
    contacts = list(Chat.objects.filter(chat_type=Chat.ChatType.CONTACT).exclude(name=""))
    ctx.log.info("Loaded %d named contacts from DB for matching", len(contacts))

    with open(TASKS_FILE) as f:
        data = json.load(f)

    if debug:
        all_assignees = set()
        for task in data["tasks"]:
            all_assignees.update(task["assignees"])
        ctx.log.info("[debug] === Assignee matching report ===")
        for name in sorted(all_assignees):
            _match_contact(name, contacts, log=ctx.log)

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
            _send_reminder(ctx, chat, task_name, None, assignee_names, contacts, today, 0, debug_log)
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
                _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, contacts, task_date, days_until, debug_log)
                ctx.log.info("Sent reminder for '%s' (due %s, assignee=%s)", task_name, task_date, assignee_name or "all")
                reminders_sent += 1
            else:
                if today != date(today.year, month, 15):
                    continue
                _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, contacts, today, 0, debug_log)
                ctx.log.info("Sent monthly reminder for '%s' (month=%d, assignee=%s)", task_name, month, assignee_name or "all")
                reminders_sent += 1

    ctx.log.info("Done. Sent %d reminder(s) today.", reminders_sent)
