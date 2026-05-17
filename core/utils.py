"""Utilities for signal-bot job scripts.

Script authors can import helpers from here:
    from core.utils import (
        send_to_all, send_picture, send_attachment,
        send_poll, get_group_members,
        mention, send_with_mentions,
        pin_message, unpin_message,
        reply,
    )
"""

from core.models import Chat, KeyValue


def store(namespace, key, value):
    """Persist a value to the database. Value can be any JSON-serializable type."""
    KeyValue.objects.update_or_create(
        namespace=namespace, key=key,
        defaults={"value": value},
    )


def load(namespace, key, default=None):
    """Load a previously stored value. Returns default if not found."""
    try:
        return KeyValue.objects.get(namespace=namespace, key=key).value
    except KeyValue.DoesNotExist:
        return default


def load_all(namespace):
    """Load all key-value pairs in a namespace as a dict."""
    return {
        kv.key: kv.value
        for kv in KeyValue.objects.filter(namespace=namespace)
    }


def delete(namespace, key):
    """Delete a stored value."""
    KeyValue.objects.filter(namespace=namespace, key=key).delete()


def delete_all(namespace):
    """Delete all stored values in a namespace."""
    KeyValue.objects.filter(namespace=namespace).delete()


def get_own_number():
    """Get the bot's own phone number."""
    from core.models import SignalAccount
    acct = SignalAccount.objects.filter(linked=True).first()
    return acct.phone_number if acct else None


def get_name(phone_number):
    """Look up a contact's display name by phone number. Returns the number itself if not found."""
    try:
        chat = Chat.objects.get(identifier=phone_number)
        return chat.name or phone_number
    except Chat.DoesNotExist:
        return phone_number


def _lookup_signalcli_recipient(aci):
    """Look up a recipient's profile in signal-cli's internal account.db by ACI (uuid)."""
    import sqlite3
    from pathlib import Path
    from django.conf import settings

    config_dir = Path(settings.SIGNAL_CLI_CONFIG) / "data"
    if not config_dir.exists():
        return None
    for db_path in config_dir.glob("*.d/account.db"):
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT number, profile_given_name, profile_family_name FROM recipient WHERE aci = ?",
                (aci,),
            ).fetchone()
            conn.close()
            if row:
                name = " ".join(filter(None, [row[1], row[2]])).strip()
                return {"number": row[0], "name": name} if name else None
        except Exception:
            pass
    return None


def get_name_from_uuid(uuid):
    """Look up a display name by UUID. Checks Chat DB first, then signal-cli's recipient DB."""
    try:
        chat = Chat.objects.get(identifier=uuid)
        if chat.name:
            return chat.name
    except Chat.DoesNotExist:
        pass
    result = _lookup_signalcli_recipient(uuid)
    if result and result["name"]:
        return result["name"]
    return uuid


def send_to_all(signal_client, chats, message, attachments=None):
    for chat in chats:
        signal_client.send_to_chat(chat, message, attachments)


def get_group_members(signal_client, chat):
    if chat.chat_type != Chat.ChatType.GROUP:
        return []
    return signal_client.get_group_members(chat.identifier)


def send_picture(signal_client, chat, file_path, caption=""):
    signal_client.send_to_chat(chat, caption or " ", attachments=[str(file_path)])


def send_attachment(signal_client, chat, file_path, message=""):
    signal_client.send_to_chat(chat, message or " ", attachments=[str(file_path)])


def send_poll(signal_client, chat, question, options, single_choice=False):
    """Send a poll. By default allows multiple selections; set single_choice=True to restrict."""
    if chat.chat_type == Chat.ChatType.GROUP:
        return signal_client.send_group_poll(
            chat.identifier, question, options, no_multi=single_choice
        )
    return signal_client.send_poll(
        chat.identifier, question, options, no_multi=single_choice
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
    placeholder = display_text or "plshldr"
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


def pin_message(signal_client, chat, target_author, target_timestamp, pin_duration=-1):
    """Pin a message in a chat. target_timestamp is the message's timestamp from the send result."""
    if chat.chat_type == Chat.ChatType.GROUP:
        return signal_client.pin_group_message(
            chat.identifier, target_author, target_timestamp, pin_duration
        )
    return signal_client.pin_message(
        chat.identifier, target_author, target_timestamp, pin_duration
    )


def unpin_message(signal_client, chat, target_author, target_timestamp):
    """Unpin a previously pinned message."""
    if chat.chat_type == Chat.ChatType.GROUP:
        return signal_client.unpin_group_message(
            chat.identifier, target_author, target_timestamp
        )
    return signal_client.unpin_message(
        chat.identifier, target_author, target_timestamp
    )


def reply(signal_client, chat, message, trigger_context, attachments=None):
    """Quote-reply to the message that triggered this job."""
    timestamp = trigger_context.get("timestamp")
    sender = trigger_context.get("sender")
    if not timestamp or not sender:
        return signal_client.send_to_chat(chat, message, attachments)
    if chat.chat_type == Chat.ChatType.GROUP:
        return signal_client.send_group_quote(
            chat.identifier, message, timestamp, sender, attachments
        )
    return signal_client.send_quote(
        chat.identifier, message, timestamp, sender, attachments
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
