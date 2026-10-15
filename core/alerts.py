"""Forward errors to the "signal dashboard alerts" Signal group.

Alerts are queued and sent from a background thread, so callers never block on
signal-cli. If signal-cli is down (which is often the error being reported),
alerts stay queued and go out once it is back.
"""

import collections
import logging
import threading
import time

logger = logging.getLogger(__name__)

ALERT_GROUP_NAME = "signal dashboard alerts"
# Identical alerts within this window are dropped, so a restart loop can't spam.
DEDUPE_SECONDS = 3600
RETRY_SECONDS = 30
MAX_QUEUED = 50
MAX_LENGTH = 1500

_queue = collections.deque(maxlen=MAX_QUEUED)
_last_sent = {}
_lock = threading.Lock()
_wakeup = threading.Event()


def send_alert(text, key=None):
    """Queue an alert. Alerts with the same key are sent at most once per hour."""
    key = key or text
    now = time.monotonic()
    with _lock:
        last = _last_sent.get(key)
        if last is not None and now - last < DEDUPE_SECONDS:
            return
        _last_sent[key] = now
        _queue.append(text[:MAX_LENGTH])
    _wakeup.set()


class AlertHandler(logging.Handler):
    """Logging handler that turns ERROR records into alerts."""

    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record):
        # Never alert about our own failures, that would loop. Job loggers are
        # skipped because the executor sends its own alert for failed jobs.
        if record.name == __name__ or record.name.startswith("job."):
            return
        try:
            text = f"[{record.name}] {record.getMessage()}"
            if record.exc_info:
                exc = record.exc_info[1]
                text += f"\n{type(exc).__name__}: {exc}"
            send_alert(text, key=f"{record.name}:{record.getMessage()}")
        except Exception:
            self.handleError(record)


def alert_loop():
    logger.info("Alert sender started")
    while True:
        _wakeup.wait(timeout=RETRY_SECONDS)
        _wakeup.clear()
        try:
            _flush()
        except Exception:
            logger.warning("Alert flush failed", exc_info=True)


def _flush():
    from core import jsonrpc
    if not _queue or not jsonrpc.is_running():
        return

    group_id = _find_group_id()
    if not group_id:
        logger.warning("No group named %r found, %d alert(s) queued", ALERT_GROUP_NAME, len(_queue))
        return

    from core.signal_client import SignalClient
    client = SignalClient()
    while _queue:
        text = _queue[0]
        try:
            client.send_group(group_id, f"⚠️ signal-bot error\n{text}")
        except Exception:
            logger.warning("Sending alert failed, will retry", exc_info=True)
            return
        _queue.popleft()


def _find_group_id():
    from core.models import Chat
    chat = Chat.objects.filter(
        chat_type=Chat.ChatType.GROUP, name__iexact=ALERT_GROUP_NAME
    ).first()
    if chat:
        return chat.identifier

    from core.signal_client import SignalClient
    for group in SignalClient().list_groups():
        if (group.get("name") or "").strip().lower() == ALERT_GROUP_NAME:
            group_id = group.get("id") or group.get("groupId")
            Chat.objects.update_or_create(
                identifier=group_id,
                defaults={"chat_type": Chat.ChatType.GROUP, "name": group.get("name")},
            )
            return group_id
    return None
