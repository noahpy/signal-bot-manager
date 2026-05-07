"""Example signal-bot script.

Every script must define a run(ctx) function.
"""


def run(ctx):
    ctx.log.info("Running example_hello script")
    for chat in ctx.target_chats:
        ctx.signal.send_to_chat(chat, "Hello from signal-bot!")
        ctx.log.info("Sent hello to %s", chat)
