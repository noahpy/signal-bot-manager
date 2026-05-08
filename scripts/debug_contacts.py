import json


def run(ctx):
    ctx.log.info("=== Fetching profiles for unknown members ===")

    unknown_uuids = [
        "31ea81b6-5c1d-41d0-8de7-b2770910205c",
        "8313203f-6dd4-4fa4-84a1-c6b5b0b7b588",
        "672559d3-89fc-4945-95ed-77b2a621bf44",
        "25304234-4e65-4f66-9c18-befaabacc574",
        "b2c368a6-7a63-4a0e-835c-3559f1f2ea92",
        "f80e8633-fb0c-4fee-8eec-2debabcf698f",
    ]

    # Try sendSyncRequest to pull contacts from phone
    ctx.log.info("=== Trying sendSyncRequest ===")
    try:
        result = ctx.signal._call("sendSyncRequest", timeout=30)
        ctx.log.info("  sendSyncRequest result: %s", result)
    except Exception as e:
        ctx.log.info("  sendSyncRequest ERROR: %s", e)

    # Try updateProfile / getProfile for each UUID
    ctx.log.info("=== Trying updateContact for each UUID ===")
    for uuid in unknown_uuids:
        try:
            result = ctx.signal._call("updateContact", timeout=10, recipient=uuid)
            ctx.log.info("  updateContact %s: %s", uuid, json.dumps(result, default=str)[:300])
        except Exception as e:
            ctx.log.info("  updateContact %s: %s", uuid, e)

    # Try sending a typing indicator (non-invasive) to force profile fetch
    ctx.log.info("=== Trying sendTyping to force profile fetch ===")
    for uuid in unknown_uuids:
        try:
            result = ctx.signal._call("sendTyping", timeout=10, recipient=[uuid])
            ctx.log.info("  sendTyping %s: %s", uuid, json.dumps(result, default=str)[:300])
        except Exception as e:
            ctx.log.info("  sendTyping %s: %s", uuid, e)

    # Now re-check contacts
    import time
    time.sleep(3)
    contacts = ctx.signal.list_contacts()
    uuid_to_contact = {c.get("uuid"): c for c in contacts if c.get("uuid")}
    ctx.log.info("=== Re-checking after profile fetch ===")
    for uuid in unknown_uuids:
        if uuid in uuid_to_contact:
            c = uuid_to_contact[uuid]
            profile = c.get("profile") or {}
            pname = " ".join(filter(None, [profile.get("givenName"), profile.get("familyName")])).strip()
            ctx.log.info("  NOW FOUND %s: number=%s profile='%s' name='%s'", uuid, c.get("number"), pname, c.get("name"))
        else:
            ctx.log.info("  STILL MISSING: %s", uuid)
