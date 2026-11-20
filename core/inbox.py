"""In-memory buffer of recent messages per chat, for the dashboard's Messages page.

Deliberately never written to disk (no DB, no logs, no backups): messages live only in
this process, at most MAX_PER_CHAT per chat and MAX_AGE seconds, and vanish on restart.

Chat keys match ``Chat.identifier``: the group id for groups, otherwise the contact's
phone number or UUID.
"""

import threading
import time
from collections import deque

MAX_PER_CHAT = 200
MAX_AGE = 24 * 60 * 60

_lock = threading.Lock()
_chats = {}  # key -> deque of message dicts


def _entry(direction, text, timestamp=None, sender="", sender_name="", attachments=0):
    return {
        "ts": (timestamp / 1000) if timestamp else time.time(),
        "direction": direction,  # "in" | "out"
        "sender": sender or "",
        "sender_name": sender_name or "",
        "text": text or "",
        "attachments": attachments,
    }


def _append(key, entry):
    from django.conf import settings
    if not key or not settings.MESSAGES_PAGE:
        return
    with _lock:
        _chats.setdefault(key, deque(maxlen=MAX_PER_CHAT)).append(entry)


def add_envelope(envelope):
    """Record an incoming signal-cli envelope (data message or sync of our own sent message)."""
    source = envelope.get("sourceNumber") or envelope.get("sourceUuid") or envelope.get("source")
    name = envelope.get("sourceName") or ""
    data = envelope.get("dataMessage")
    if data and (data.get("message") or data.get("attachments")):
        group = (data.get("groupInfo") or {}).get("groupId")
        _append(group or source, _entry(
            "in", data.get("message"), data.get("timestamp") or envelope.get("timestamp"),
            source, name, len(data.get("attachments") or [])))
        return
    sent = (envelope.get("syncMessage") or {}).get("sentMessage")
    if sent and (sent.get("message") or sent.get("attachments")):
        group = (sent.get("groupInfo") or {}).get("groupId")
        dest = sent.get("destinationNumber") or sent.get("destinationUuid") or sent.get("destination")
        _append(group or dest, _entry(
            "out", sent.get("message"), sent.get("timestamp"), source, name,
            len(sent.get("attachments") or [])))


def add_outgoing(key, text, attachments=0):
    """Record a message the bot itself sent (jobs, reminders, dashboard)."""
    _append(key, _entry("out", text, attachments=attachments))


def _prune_locked():
    cutoff = time.time() - MAX_AGE
    for key in list(_chats):
        q = _chats[key]
        if any(m["ts"] < cutoff for m in q):  # timestamps may arrive out of order (backlog)
            q = _chats[key] = deque((m for m in q if m["ts"] >= cutoff), maxlen=MAX_PER_CHAT)
        if not q:
            del _chats[key]


def messages(key):
    with _lock:
        _prune_locked()
        return sorted(_chats.get(key, ()), key=lambda m: m["ts"])


def summary():
    """key -> (number of buffered messages, timestamp of the last one)."""
    with _lock:
        _prune_locked()
        return {k: (len(q), max(m["ts"] for m in q)) for k, q in _chats.items()}


def clear():
    with _lock:
        _chats.clear()
