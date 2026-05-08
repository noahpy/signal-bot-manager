
import tempfile
import os

from core.utils import (
    send_poll,
    get_group_members,
    mention,
    send_with_mentions,
    pin_message,
    get_name,
    load,
    store
)

NAMESPAE = "kkk-weekly"
LAST_DECIDER_STATS_KEY = "last-decider-stats"

def run(ctx):
    ctx.log.info("=== KKK weekly digest ===")

    chat = ctx.target_chats[0]

    members = get_group_members(ctx.signal, chat)
    ctx.log.info("Group %s has %d members", chat.name, len(members))

    last_decider_stats = load(NAMESPAE, LAST_DECIDER_STATS_KEY)

    if not last_decider_stats:
        last_decider_stats = [(0, p['number']) for p in members]
        last_decider_stats.sort()

    next_decider_num = last_decider_stats[0][1]
    next_decider_name = get_name(next_decider_num)

    text, m = mention(next_decider_num)
    msg = f"Hey, {text}! Diese Woche ist deine Woche um KKK zu bestimmen. Gib Ort / Uhrzeit vor und pinne die Nachricht! Reservieren wenn notwendig! Unten kommt noch eine Umfrage."

    send_with_mentions(ctx.signal, chat, msg, [m(msg.index(text))])

    res = send_poll(ctx.signal, chat, "Wann KKK?", ["Freitag", "Samstag", "Sonntag"])












