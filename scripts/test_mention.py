"""Send a test message to the target group that @mentions members by UUID (not phone number)."""

from core.models import SignalAccount
from core.utils import get_group_members, mention, send_with_mentions


def run(ctx):
    chat = ctx.target_chats[0]
    own = SignalAccount.objects.filter(linked=True).values_list("phone_number", flat=True).first()
    members = [m for m in get_group_members(ctx.signal, chat) if m.get("uuid")]
    others = [m for m in members if m.get("number") != own]
    targets = others or members
    ctx.log.info("Mentioning %d member(s) by UUID: %s", len(targets), [m["uuid"] for m in targets])
    if not targets:
        raise RuntimeError("No group members with a known UUID")

    parts = [mention(m["uuid"], m.get("name") or m.get("profileName") or "Mitglied") for m in targets]
    msg = "Test: Erwähnung per UUID -> " + ", ".join(text for text, _ in parts)
    specs = []
    pos = len("Test: Erwähnung per UUID -> ")
    for text, build in parts:
        pos = msg.index(text, pos)
        specs.append(build(pos))
        pos += len(text)
    result = send_with_mentions(ctx.signal, chat, msg, specs)
    ctx.log.info("Sent: %s | mentions=%s | result=%s", msg, specs, result)
