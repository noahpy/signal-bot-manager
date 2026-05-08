
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
    store,
    get_own_number
)

NAMESPACE = "kkk-weekly"
LAST_DECIDER_STATS_KEY = "last-decider-stats"

def not_in_absent(number, absents) -> str | None:
    name = get_name(number)
    for absent in absents:
        if name.lower().find(absent.lower()) != -1:
            return None
    return name


def run(ctx):
    ctx.log.info("=== KKK weekly digest ===")

    chat = ctx.target_chats[0]

    members = get_group_members(ctx.signal, chat)
    ctx.log.info("Group %s has %d members", chat.name, len(members))

    last_decider_stats = load(NAMESPACE, LAST_DECIDER_STATS_KEY)

    if not last_decider_stats:
        last_decider_stats_list = [(p['number'], 0) for p in members]
        last_decider_stats = dict(last_decider_stats_list)
    else:
        last_decider_stats_list = list(last_decider_stats.items())

    last_decider_stats_list.sort(key=lambda x: (x[1], x[0]))

    absent_list = ctx.config['absent']
    next_decider_num = None

    for candidate in last_decider_stats_list:
        if (name := not_in_absent(candidate[0], absent_list)) is None:
            continue
        next_decider_name = name
        next_decider_num = candidate[0]
        break

    if next_decider_num is None:
        ctx.signal.send_to_chat(chat, "No one present! See you next week!")
        return

    text, m = mention(next_decider_num)

    if next_decider_name.lower().find("fabi") != -1:
        msg = f"Hey, {text}! Diese Woche ist deine Woche um KKK zu bestimmen. Gebe Ort / Uhrzeit vor und pinne die Nachricht! Reservieren wenn notwendig! Unten kommt noch eine Umfrage."
    else:
        msg = f"Hey, {text}! Diese Woche ist deine Woche um KKK zu bestimmen. Gib Ort / Uhrzeit vor und pinne die Nachricht! Reservieren wenn notwendig! Unten kommt noch eine Umfrage."

    send_with_mentions(ctx.signal, chat, msg, [m(msg.index(text))])

    res = send_poll(ctx.signal, chat, "Wann KKK?", ["14.00", "14.30", "15.00", "15.30", "16.00"])
    pin_message(ctx.signal, chat, get_own_number(), res["timestamp"], 400000)

    last_decider_stats[next_decider_num] += 1

    store(NAMESPACE, LAST_DECIDER_STATS_KEY, last_decider_stats)

    











