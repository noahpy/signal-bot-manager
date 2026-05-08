"""Test script for utility functions. Run against Note to Self chat."""

import tempfile
import os

from core.utils import (
    send_to_all,
    send_picture,
    send_attachment,
    send_poll,
    get_group_members,
    mention,
    send_with_mentions,
    pin_message,
)


def run(ctx):
    ctx.log.info("=== Testing utility functions ===")
    chat = ctx.target_chats[0]

    # 1. send_to_all
    ctx.log.info("Test 1: send_to_all")
    send_to_all(ctx.signal, ctx.target_chats, "Test 1: send_to_all works!")

    # 2. Send an attachment
    ctx.log.info("Test 2: send_attachment")
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("This is a test attachment from signal-bot.")
        tmp_path = f.name
    try:
        send_attachment(ctx.signal, chat, tmp_path, "Test 2: attachment")
    finally:
        os.unlink(tmp_path)

    # 3. Send a poll
    ctx.log.info("Test 3: send_poll")
    send_poll(ctx.signal, chat, "Test poll: pick a color", ["Red", "Green", "Blue"])

    # 4. Send a single-choice poll
    ctx.log.info("Test 4: send_poll (single choice)")
    send_poll(ctx.signal, chat, "Single choice poll", ["Yes", "No"], single_choice=True)

    # 5. Mention (self-mention in Note to Self)
    ctx.log.info("Test 5: mention")
    from core.models import SignalAccount
    acct = SignalAccount.objects.filter(linked=True).first()
    if acct:
        placeholder, m = mention(acct.phone_number, "@Me")
        message = f"Test 5: Hello {placeholder}, this is a mention test!"
        specs = [m(message.index(placeholder))]
        send_with_mentions(ctx.signal, chat, message, specs)

    # 6. Pin a message (send one then pin it)
    ctx.log.info("Test 6: pin_message")
    result = ctx.signal.send_to_chat(chat, "Test 6: Pin this message!")
    if result and result.get("timestamp"):
        ts = result["timestamp"]
        from core.models import SignalAccount
        acct = SignalAccount.objects.filter(linked=True).first()
        if acct:
            pin_message(ctx.signal, chat, acct.phone_number, ts)
            ctx.log.info("Pinned message with timestamp %s", ts)

    # 7. Get group members (skip for contact chats)
    ctx.log.info("Test 7: get_group_members")
    for c in ctx.target_chats:
        if c.chat_type == "group":
            members = get_group_members(ctx.signal, c)
            ctx.log.info("Group %s has %d members", c.name, len(members))
        else:
            ctx.log.info("Skipping get_group_members for contact: %s", c.name)

    ctx.log.info("=== All utility tests complete ===")
