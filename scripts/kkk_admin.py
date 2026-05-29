import re

from core.utils import (
    get_group_members,
    get_name,
    load,
    store,
    delete,
    reply,
)

NAMESPACE = "kkk-weekly"
LAST_DECIDER_STATS_KEY = "last-decider-stats"
OVERRIDE_KEY = "next-override"

ADMIN_NAMES = ["noah"]

HELP_TEXT = (
    "KKK Bot Befehle:\n"
    "!kkk stats — Histogramm der Entscheidungen\n"
    "!kkk next — Wer ist als nächstes dran?\n"
    "\n"
    "Admin:\n"
    "!kkk override <name> [nocount] — Override für nächste Woche\n"
    "!kkk set <name> <zahl> — Statistik setzen\n"
    "!kkk clearoverride — Override löschen\n"
    "!kkk help — Diese Hilfe"
)


def _get_stats_and_members(ctx):
    chat = ctx.target_chats[0]
    members = get_group_members(ctx.signal, chat)
    stats = load(NAMESPACE, LAST_DECIDER_STATS_KEY)
    if not stats:
        stats = {p["number"]: 0 for p in members}
    return stats, members


def _find_member_by_name(query, stats):
    query_lower = query.lower()
    for num in stats:
        name = get_name(num)
        if name.lower().find(query_lower) != -1:
            return num, name
    return None, None


def _is_admin(sender_name):
    sender_lower = sender_name.lower()
    for admin in ADMIN_NAMES:
        if sender_lower.find(admin.lower()) != -1:
            return True
    return False


def _build_histogram(stats):
    named = sorted(
        [(get_name(num), count) for num, count in stats.items()],
        key=lambda x: (-x[1], x[0]),
    )
    if not named:
        return "(keine Daten)"

    max_count = max(c for _, c in named)
    max_name_len = max(len(n) for n, _ in named)
    bar_width = 20

    lines = []
    for name, count in named:
        if max_count > 0:
            bar_len = round(count / max_count * bar_width)
        else:
            bar_len = 0
        bar = "█" * bar_len + "░" * (bar_width - bar_len)
        lines.append(f"{name:<{max_name_len}} |{bar}| {count}")
    return "\n".join(lines)


def _forecast_next(stats, absent_list):
    stats_list = sorted(stats.items(), key=lambda x: (x[1], x[0]))
    for num, _count in stats_list:
        name = get_name(num)
        if all(name.lower().find(a.lower()) == -1 for a in absent_list):
            return name
    return None


def _cmd_stats(ctx):
    stats, _ = _get_stats_and_members(ctx)
    histogram = _build_histogram(stats)
    override = load(NAMESPACE, OVERRIDE_KEY)
    msg = f"KKK Entscheidungs-Statistik:\n\n{histogram}"
    if override:
        counts_str = "zählt" if override.get("counts", True) else "zählt nicht"
        msg += f"\n\nOverride nächste Woche: {override['name']} ({counts_str})"
    reply(ctx.signal, ctx.target_chats[0], msg, ctx.trigger_context)


def _cmd_next(ctx):
    stats, _ = _get_stats_and_members(ctx)
    absent_list = ctx.config.get("absent", [])

    override = load(NAMESPACE, OVERRIDE_KEY)
    if override:
        counts_str = "zählt" if override.get("counts", True) else "zählt nicht"
        msg = f"Nächste Woche (Override): {override['name']} ({counts_str})"
    else:
        name = _forecast_next(stats, absent_list)
        if name:
            msg = f"Nächster Entscheider (Prognose): {name}"
        else:
            msg = "Keiner verfügbar!"
    reply(ctx.signal, ctx.target_chats[0], msg, ctx.trigger_context)


def _cmd_override(ctx, args, sender_name):
    if not _is_admin(sender_name):
        reply(ctx.signal, ctx.target_chats[0], "Nur Admins können Overrides setzen.", ctx.trigger_context)
        return

    parts = args.strip().split()
    if not parts:
        reply(ctx.signal, ctx.target_chats[0], "Nutzung: !kkk override <name> [nocount]", ctx.trigger_context)
        return

    name_query = parts[0]
    counts = "nocount" not in [p.lower() for p in parts[1:]]

    stats, _ = _get_stats_and_members(ctx)
    num, resolved_name = _find_member_by_name(name_query, stats)
    if not num:
        reply(ctx.signal, ctx.target_chats[0], f"Kein Mitglied gefunden für '{name_query}'.", ctx.trigger_context)
        return

    override_data = {"name": resolved_name, "number": num, "counts": counts}
    store(NAMESPACE, OVERRIDE_KEY, override_data)
    counts_str = "zählt" if counts else "zählt nicht"
    reply(ctx.signal, ctx.target_chats[0], f"Override gesetzt: {resolved_name} ({counts_str})", ctx.trigger_context)


def _cmd_clear_override(ctx, sender_name):
    if not _is_admin(sender_name):
        reply(ctx.signal, ctx.target_chats[0], "Nur Admins können Overrides löschen.", ctx.trigger_context)
        return
    delete(NAMESPACE, OVERRIDE_KEY)
    reply(ctx.signal, ctx.target_chats[0], "Override gelöscht.", ctx.trigger_context)


def _cmd_set(ctx, args, sender_name):
    if not _is_admin(sender_name):
        reply(ctx.signal, ctx.target_chats[0], "Nur Admins können Stats setzen.", ctx.trigger_context)
        return

    parts = args.strip().split()
    if len(parts) < 2:
        reply(ctx.signal, ctx.target_chats[0], "Nutzung: !kkk set <name> <zahl>", ctx.trigger_context)
        return

    name_query = parts[0]
    try:
        new_count = int(parts[1])
    except ValueError:
        reply(ctx.signal, ctx.target_chats[0], f"'{parts[1]}' ist keine gültige Zahl.", ctx.trigger_context)
        return

    stats, _ = _get_stats_and_members(ctx)
    num, resolved_name = _find_member_by_name(name_query, stats)
    if not num:
        reply(ctx.signal, ctx.target_chats[0], f"Kein Mitglied gefunden für '{name_query}'.", ctx.trigger_context)
        return

    stats[num] = new_count
    store(NAMESPACE, LAST_DECIDER_STATS_KEY, stats)
    reply(ctx.signal, ctx.target_chats[0], f"Stats für {resolved_name} auf {new_count} gesetzt.", ctx.trigger_context)


def run(ctx):
    ctx.log.info("=== KKK Admin ===")
    message = ctx.trigger_context.get("message", "")
    sender = ctx.trigger_context.get("sender")
    ctx.log.info("From %s: %s", sender, message[:100])

    sender_name = get_name(sender) if sender else ""
    msg_lower = message.lower().strip()

    match = re.match(r"!kkk\s+(\w+)\s*(.*)", msg_lower, re.DOTALL)
    if not match:
        reply(ctx.signal, ctx.target_chats[0], HELP_TEXT, ctx.trigger_context)
        return

    cmd = match.group(1)
    args = match.group(2).strip()

    # preserve original case for name arguments
    orig_match = re.match(r"!kkk\s+\w+\s*(.*)", message.strip(), re.DOTALL)
    orig_args = orig_match.group(1).strip() if orig_match else args

    if cmd == "stats":
        _cmd_stats(ctx)
    elif cmd == "next":
        _cmd_next(ctx)
    elif cmd == "override":
        _cmd_override(ctx, orig_args, sender_name)
    elif cmd in ("clearoverride", "clear"):
        _cmd_clear_override(ctx, sender_name)
    elif cmd == "set":
        _cmd_set(ctx, orig_args, sender_name)
    elif cmd == "help":
        reply(ctx.signal, ctx.target_chats[0], HELP_TEXT, ctx.trigger_context)
    else:
        reply(ctx.signal, ctx.target_chats[0], f"Unbekannter Befehl: {cmd}\n\n{HELP_TEXT}", ctx.trigger_context)
