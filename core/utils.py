"""Utilities for signal-bot job scripts.

Script authors can import helpers from here:
    from core.utils import send_to_all, mention, send_poll, send_picture, get_group_members
"""

from core.models import Chat
from core.signal_client import SignalClient


def send_to_all(signal_client, chats, message, attachments=None):
    for chat in chats:
        signal_client.send_to_chat(chat, message, attachments)


def get_group_members(signal_client, chat):
    if chat.chat_type != Chat.ChatType.GROUP:
        return []
    return signal_client.get_group_members(chat.identifier)


def send_picture(signal_client, chat, file_path, caption=""):
    signal_client.send_to_chat(chat, caption, attachments=[str(file_path)])


def send_attachment(signal_client, chat, file_path, message=""):
    signal_client.send_to_chat(chat, message, attachments=[str(file_path)])


def send_poll(signal_client, chat, question, options, multi_vote=False):
    if chat.chat_type == Chat.ChatType.GROUP:
        return signal_client.send_group_poll(
            chat.identifier, question, options, multi_vote
        )
    return signal_client.send_poll(
        chat.identifier, question, options, multi_vote
    )


def mention(phone_number, display_text=None):
    """Build a mention placeholder and spec for use with send_with_mentions().

    Returns (placeholder_text, mention_spec_builder) where placeholder_text
    should be inserted into the message and mention_spec_builder is called
    with the final start position.

    Usage:
        text, m = mention("+49176...", "Alice")
        message = f"Hey {text}, check this!"
        mentions = [m(message.index(text))]
        signal_client.send_group_with_mention(group_id, message, mentions)
    """
    placeholder = f"￼" if not display_text else display_text
    length = len(placeholder.encode("utf-16-le")) // 2

    def build(start_position):
        return f"{start_position}:{length}:{phone_number}"

    return placeholder, build


def send_with_mentions(signal_client, chat, message, mention_specs, attachments=None):
    """Send a message with @mentions.

    mention_specs: list of "start:length:phone" strings (use mention() helper to build these)
    """
    if chat.chat_type == Chat.ChatType.GROUP:
        return signal_client.send_group_with_mention(
            chat.identifier, message, mention_specs, attachments
        )
    return signal_client.send_with_mention(
        chat.identifier, message, mention_specs, attachments
    )


def format_table(headers, rows):
    if not rows:
        return "(empty)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    def _fmt_row(cells):
        return " | ".join(str(c).ljust(w) for c, w in zip(cells, col_widths))

    lines = [_fmt_row(headers)]
    lines.append("-+-".join("-" * w for w in col_widths))
    for row in rows:
        lines.append(_fmt_row(row))
    return "\n".join(lines)
