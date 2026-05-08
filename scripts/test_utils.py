"""Test script for utility functions. Run against Note to Self chat."""

import tempfile
import os

from core.utils import (
    send_to_all,
    send_picture,
    send_attachment,
    send_poll,
    get_group_members,
)


def run(ctx):
    ctx.log.info("=== Testing utility functions ===")

    # 1. send_to_all
    ctx.log.info("Test: send_to_all")
    send_to_all(ctx.signal, ctx.target_chats, "Test: send_to_all works!")

    # 2. Send a picture (create a simple text file as a test attachment)
    ctx.log.info("Test: send_picture")
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("This is a test attachment from signal-bot.")
        tmp_path = f.name
    try:
        send_attachment(ctx.signal, ctx.target_chats[0], tmp_path, "Test: attachment works!")
    finally:
        os.unlink(tmp_path)

    # 3. Send a poll
    ctx.log.info("Test: send_poll")
    send_poll(
        ctx.signal,
        ctx.target_chats[0],
        "Test poll: pick a color",
        ["Red", "Green", "Blue"],
        multi_vote=False,
    )

    # 4. Get group members (only if target is a group)
    for chat in ctx.target_chats:
        if chat.chat_type == "group":
            ctx.log.info("Test: get_group_members for %s", chat.name)
            members = get_group_members(ctx.signal, chat)
            ctx.log.info("Members: %s", members)
        else:
            ctx.log.info("Skipping get_group_members for contact chat: %s", chat.name)

    ctx.log.info("=== All utility tests complete ===")
