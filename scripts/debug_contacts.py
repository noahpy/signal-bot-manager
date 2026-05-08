import json


def run(ctx):
    ctx.log.info("=== Debug Contacts ===")
    contacts = ctx.signal.list_contacts()
    ctx.log.info("Total contacts from listContacts: %d", len(contacts))

    with_num = [c for c in contacts if c.get("number")]
    without_num = [c for c in contacts if not c.get("number")]
    ctx.log.info("With number: %d, Without number: %d", len(with_num), len(without_num))

    ctx.log.info("=== WITHOUT number (first 10) ===")
    for c in without_num[:10]:
        keys = list(c.keys())
        ctx.log.info("  keys: %s", keys)
        subset = {k: c.get(k) for k in ["number", "uuid", "name", "contactName", "profileName", "profile", "username"] if c.get(k)}
        ctx.log.info("  %s", json.dumps(subset, default=str))

    ctx.log.info("=== WITH number (first 5) ===")
    for c in with_num[:5]:
        subset = {k: c.get(k) for k in ["number", "uuid", "name", "contactName", "profileName", "profile", "username"] if c.get(k)}
        ctx.log.info("  %s", json.dumps(subset, default=str))

    # Also check group members raw data
    groups = ctx.signal.list_groups()
    for g in groups:
        gid = g.get("id") or g.get("groupId")
        if gid == "t9xo6lcGLNbVvcfiG56PCM/j1IcHLaXwEoOUPJKABU8=":
            members = g.get("members", [])
            ctx.log.info("=== H2F4 Tasks members (first 5 raw) ===")
            for m in members[:5]:
                ctx.log.info("  %s", json.dumps(m, default=str))
            break
