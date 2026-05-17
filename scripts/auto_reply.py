import re

from core.utils import reply


RULES = [
    (r"(?i)\bping\b", "Pong!"),
    (r"(?i)\bhello\b", "Hey there!"),
    (r"(?i)\bhelp\b", "Available commands: ping, hello, help"),
]


def run(ctx):
    ctx.log.info("=== Auto Reply ===")
    message = ctx.trigger_context.get("message", "")
    sender = ctx.trigger_context.get("sender")
    ctx.log.info("Received from %s: %s", sender, message[:100])

    chat = ctx.target_chats[0]

    for pattern, response in RULES:
        if re.search(pattern, message):
            ctx.log.info("Matched pattern '%s', replying: %s", pattern, response)
            reply(ctx.signal, chat, response, ctx.trigger_context)
            return

    ctx.log.info("No matching rule, ignoring message")
