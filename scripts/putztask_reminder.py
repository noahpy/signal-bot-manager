import json
from datetime import date, timedelta
from pathlib import Path

from core.models import Chat
from core.utils import (
    _lookup_signalcli_recipient,
    get_group_members,
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
    low = date_str.strip().lower()
    if low in GERMAN_MONTHS:
        return GERMAN_MONTHS[low], None
    parts = date_str.strip().split(".")
    if len(parts) == 2:
        return int(parts[1]), int(parts[0])
    return None, None


def _part_matches(query_part, full_part):
    is_abbrev = query_part.endswith(".")
    qp = query_part.rstrip(".")
    fp = full_part.rstrip(".")
    if not qp or not fp:
        return False
    if not is_abbrev and (len(qp) < 2 or len(fp) < 2):
        return False
    return qp.startswith(fp) or fp.startswith(qp)


def _resolve_members(signal_client, chat):
    """Get group members and resolve their names via Chat DB, falling back to signal-cli's recipient DB."""
    raw_members = get_group_members(signal_client, chat)
    members = []
    for m in raw_members:
        uuid = m.get("uuid")
        number = m.get("number")
        name = None
        # Try Chat DB lookup by uuid
        if uuid:
            try:
                name = Chat.objects.get(identifier=uuid).name
            except Chat.DoesNotExist:
                pass
        # Try Chat DB lookup by number
        if number:
            try:
                num_name = Chat.objects.get(identifier=number).name
                if not name:
                    name = num_name
            except Chat.DoesNotExist:
                pass
        # Fallback: signal-cli's recipient table
        if not name and uuid:
            result = _lookup_signalcli_recipient(uuid)
            if result:
                name = result["name"]
                if not number and result.get("number"):
                    number = result["number"]
        identifier = number or uuid
        members.append({"identifier": identifier, "name": name or "", "number": number, "uuid": uuid})
    return members


def _match_member(name, members, log=None):
    name_lower = name.lower()
    name_parts = name_lower.split()
    best = None
    best_score = -1
    for m in members:
        full = m["name"].lower()
        if not full or len(full) < 2:
            continue
        if name_lower == full:
            if log:
                log.info("  [debug] '%s' -> exact match: %s (%s)", name, m["identifier"], m["name"])
            return m
        full_parts = full.split()
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
                best = m
    if log and best:
        log.info("  [debug] '%s' -> best match: %s (%s)", name, best["identifier"], best["name"])
    elif log:
        log.info("  [debug] '%s' -> NO MATCH FOUND", name)
    return best


def _is_phone(identifier):
    return identifier and identifier.startswith("+")


def _build_mentions(members_to_mention):
    """Build mention texts and builders for a list of members. Returns (texts, builders) lists."""
    texts = []
    builders = []
    plain_names = []
    for m in members_to_mention:
        display = m["name"] or m["identifier"]
        if _is_phone(m["identifier"]):
            text, builder = mention(m["identifier"], display)
            texts.append(text)
            builders.append((text, builder))
        else:
            plain_names.append(display)
    return texts + plain_names, builders


def _send_reminder(ctx, chat, task_name, assignee_name, assignee_names, members, task_date, days_until, debug_log=None):
    if days_until == 0:
        timing = "die heute dran ist :)"
    else:
        timing = f"die am {task_date.strftime('%d.%m.')} geplant ist (in {days_until} Tagen) :)"

    # Resolve who to mention
    if assignee_name:
        matched = _match_member(assignee_name, members, log=debug_log)
        to_mention = [matched] if matched else []
        fallback_names = [assignee_name] if not matched else []
    else:
        to_mention = [m for m in (_match_member(a, members, log=debug_log) for a in assignee_names) if m]
        fallback_names = assignee_names if not to_mention else []

    if to_mention:
        name_parts, builders = _build_mentions(to_mention)
        names_str = ", ".join(name_parts)
        msg = f"Hey {names_str}, eine Erinnerung für die Task \"{task_name}\" {timing}."
        specs = []
        for text, builder in builders:
            idx = msg.index(text)
            specs.append(builder(idx))
        if specs:
            send_with_mentions(ctx.signal, chat, msg, specs)
        else:
            ctx.signal.send_to_chat(chat, msg)
    else:
        names_str = ", ".join(fallback_names)
        msg = f"Hey {names_str}, eine Erinnerung für die Task \"{task_name}\" {timing}."
        ctx.signal.send_to_chat(chat, msg)


def run(ctx):
    ctx.log.info("=== Putztask Reminder ===")
    debug = ctx.config.get("debug", False)
    debug_log = ctx.log if debug else None

    chat = ctx.target_chats[0]
    members = _resolve_members(ctx.signal, chat)
    ctx.log.info("Group '%s' has %d members (%d with names)", chat.name, len(members), sum(1 for m in members if m["name"]))

    with open(TASKS_FILE) as f:
        data = json.load(f)

    if debug:
        ctx.log.info("[debug] === Group members ===")
        for m in members:
            ctx.log.info("  [debug] %s -> '%s'", m["identifier"], m["name"] or "(no name)")
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
