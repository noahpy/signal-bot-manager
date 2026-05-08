"""Test script for utility functions. Run against Note to Self chat."""

import tempfile
import os

from core.utils import (
    send_to_all,
    send_attachment,
    send_poll,
    get_group_members,
    get_name,
    store,
    load,
    load_all,
    delete,
)


def run(ctx):
    ctx.log.info("=== Testing utility functions ===")
    chat = ctx.target_chats[0]
    from core.models import SignalAccount
    acct = SignalAccount.objects.filter(linked=True).first()

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

    # 4. get_name
    ctx.log.info("Test 4: get_name")
    if acct:
        name = get_name(acct.phone_number)
        ctx.log.info("  get_name(%s) = %s", acct.phone_number, name)
    unknown = get_name("+0000000000")
    ctx.log.info("  get_name(unknown) = %s", unknown)
    results = []
    results.append(f"Own number: {get_name(acct.phone_number)}" if acct else "No account")
    results.append(f"Unknown: {unknown}")
    ctx.signal.send_to_chat(chat, "Test 4 get_name:\n" + "\n".join(results))

    # 5. store / load / load_all / delete
    ctx.log.info("Test 5: store/load")
    store("test_utils", "last_run", "just now")
    store("test_utils", "counter", 42)
    store("test_utils", "tags", ["alpha", "beta"])

    v1 = load("test_utils", "last_run")
    v2 = load("test_utils", "counter")
    v3 = load("test_utils", "tags")
    v_missing = load("test_utils", "nope", "default_val")
    ctx.log.info("  last_run=%s counter=%s tags=%s missing=%s", v1, v2, v3, v_missing)

    all_kv = load_all("test_utils")
    ctx.log.info("  load_all: %s", all_kv)

    delete("test_utils", "tags")
    after_delete = load("test_utils", "tags", "DELETED")
    ctx.log.info("  after delete tags: %s", after_delete)

    # Increment counter to prove persistence across runs
    prev = load("test_utils", "run_count", 0)
    store("test_utils", "run_count", prev + 1)
    ctx.log.info("  run_count: %d -> %d", prev, prev + 1)

    ctx.signal.send_to_chat(chat,
        f"Test 5 store/load:\n"
        f"  last_run={v1}\n"
        f"  counter={v2}\n"
        f"  tags={v3}\n"
        f"  missing={v_missing}\n"
        f"  all_keys={list(all_kv.keys())}\n"
        f"  after_delete_tags={after_delete}\n"
        f"  run_count={prev + 1}"
    )

    # 6. Get group members (skip for contact chats)
    ctx.log.info("Test 6: get_group_members")
    for c in ctx.target_chats:
        if c.chat_type == "group":
            members = get_group_members(ctx.signal, c)
            ctx.log.info("Group %s has %d members", c.name, len(members))
        else:
            ctx.log.info("Skipping get_group_members for contact: %s", c.name)

    ctx.log.info("=== All utility tests complete ===")
