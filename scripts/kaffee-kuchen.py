
import tempfile
import os

from core.utils import (
    send_poll,
    get_group_members,
    mention,
    send_with_mentions,
    pin_message,
    get_name
)


def run(ctx):
    ctx.log.info("=== KKK weekly digest ===")

    chat = ctx.target_chats[0]

    members = get_group_members(ctx.signal, chat)
    ctx.log.info("Group %s has %d members", chat.name, len(members))

    msg = f"Group {chat.name} has {len(members)} members: {members}"
    ctx.signal.send_to_chat(chat, msg)
