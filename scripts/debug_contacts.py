import json


def run(ctx):
    ctx.log.info("=== Debug Unknown Members ===")

    # The 6 unnamed member UUIDs from H2F4 Tasks
    unknown_uuids = [
        "31ea81b6-5c1d-41d0-8de7-b2770910205c",
        "8313203f-6dd4-4fa4-84a1-c6b5b0b7b588",
        "672559d3-89fc-4945-95ed-77b2a621bf44",
        "25304234-4e65-4f66-9c18-befaabacc574",
        "b2c368a6-7a63-4a0e-835c-3559f1f2ea92",
        "f80e8633-fb0c-4fee-8eec-2debabcf698f",
    ]

    # Check if these UUIDs appear in listContacts
    contacts = ctx.signal.list_contacts()
    ctx.log.info("Total contacts: %d", len(contacts))

    uuid_to_contact = {}
    for c in contacts:
        u = c.get("uuid")
        if u:
            uuid_to_contact[u] = c

    ctx.log.info("=== Checking unknown UUIDs against contacts ===")
    for uuid in unknown_uuids:
        if uuid in uuid_to_contact:
            c = uuid_to_contact[uuid]
            profile = c.get("profile") or {}
            ctx.log.info("  FOUND %s in contacts:", uuid)
            ctx.log.info("    number: %s", c.get("number"))
            ctx.log.info("    name: %s", c.get("name"))
            ctx.log.info("    contactName: %s", c.get("contactName"))
            ctx.log.info("    profileName: %s", c.get("profileName"))
            ctx.log.info("    givenName: %s", c.get("givenName"))
            ctx.log.info("    profile.givenName: %s", profile.get("givenName"))
            ctx.log.info("    profile.familyName: %s", profile.get("familyName"))
            ctx.log.info("    unregistered: %s", c.get("unregistered"))
        else:
            ctx.log.info("  NOT IN CONTACTS: %s", uuid)

    # Also check: does the group itself have any extra member info?
    groups = ctx.signal.list_groups()
    for g in groups:
        gid = g.get("id") or g.get("groupId")
        if gid == "t9xo6lcGLNbVvcfiG56PCM/j1IcHLaXwEoOUPJKABU8=":
            members = g.get("members", [])
            ctx.log.info("=== Raw member data for unknown UUIDs ===")
            for m in members:
                if m.get("uuid") in unknown_uuids:
                    ctx.log.info("  %s", json.dumps(m, default=str))
            # Check if there are other fields on the group
            ctx.log.info("=== Group keys: %s ===", list(g.keys()))
            # Check pendingMembers, requestingMembers, etc.
            for key in ["pendingMembers", "requestingMembers", "bannedMembers", "admins"]:
                if g.get(key):
                    ctx.log.info("  %s: %s", key, json.dumps(g[key], default=str)[:500])
            break

    # Try getUserStatus or getIdentity for these UUIDs
    ctx.log.info("=== Trying getUserStatus for unknown UUIDs ===")
    for uuid in unknown_uuids:
        try:
            result = ctx.signal._call("getUserStatus", timeout=10, recipient=[uuid])
            ctx.log.info("  getUserStatus %s: %s", uuid, json.dumps(result, default=str)[:300])
        except Exception as e:
            ctx.log.info("  getUserStatus %s: ERROR %s", uuid, e)

    ctx.log.info("=== Trying listIdentities ===")
    try:
        identities = ctx.signal._call("listIdentities", timeout=30)
        ctx.log.info("Total identities: %d", len(identities) if isinstance(identities, list) else "not a list")
        if isinstance(identities, list):
            for ident in identities:
                if ident.get("uuid") in unknown_uuids or ident.get("number") in [None]:
                    # Check if any identity matches our unknown UUIDs
                    for uuid in unknown_uuids:
                        if str(ident).find(uuid) != -1:
                            ctx.log.info("  Identity match: %s", json.dumps(ident, default=str)[:300])
    except Exception as e:
        ctx.log.info("  listIdentities ERROR: %s", e)
