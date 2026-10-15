import logging
import re
import time

from core.alerts import send_alert
from core.executor import execute_job
from core.models import SignalAccount, Trigger

logger = logging.getLogger(__name__)


RESTART_DELAY_MIN = 5
RESTART_DELAY_MAX = 300
# detect_account() boots a JVM, so poll for an account slowly while unlinked.
NO_ACCOUNT_DELAY = 60
# Messages older than this (e.g. a backlog delivered after downtime) are not
# matched against triggers, so the bot doesn't answer stale messages.
MAX_MESSAGE_AGE = 5 * 60


def listener_loop():
    logger.info("Message listener started")
    restart_delay = RESTART_DELAY_MIN
    while True:
        try:
            acct = SignalAccount.objects.filter(linked=True).first()
            if not acct or not acct.phone_number:
                from core.signal_client import detect_account
                phone = detect_account()
                if not phone:
                    logger.info("No linked account, waiting...")
                    time.sleep(NO_ACCOUNT_DELAY)
                    continue
                acct = SignalAccount.objects.filter(linked=True).first()
                if not acct or not acct.phone_number:
                    time.sleep(NO_ACCOUNT_DELAY)
                    continue

            from core import jsonrpc
            if not jsonrpc.is_running():
                logger.info("Starting shared jsonRpc process for %s", acct.phone_number)
                jsonrpc.start(acct.phone_number, on_notification=_handle_notification)

            started_at = time.monotonic()
            while jsonrpc.is_running():
                time.sleep(1)
            uptime = time.monotonic() - started_at

            stderr = jsonrpc.last_stderr()
            if "not registered" in stderr.lower():
                logger.error(
                    "signal-cli reports the account is no longer registered - the "
                    "linked device was removed. Re-link the bot in the dashboard "
                    "(Account > Start Linking). signal-cli output: %s",
                    stderr,
                )
                SignalAccount.objects.filter(linked=True).update(linked=False)
                continue

            if uptime > 60:
                restart_delay = RESTART_DELAY_MIN
            send_alert(
                f"signal-cli died after {uptime:.0f}s, restarting in {restart_delay}s\n"
                + "\n".join(stderr.splitlines()[-5:]),
                key="jsonrpc-died",
            )
            logger.warning(
                "jsonRpc process died after %.0fs, restarting in %ds... %s",
                uptime, restart_delay, stderr,
            )
            time.sleep(restart_delay)
            restart_delay = min(restart_delay * 2, RESTART_DELAY_MAX)
        except Exception:
            logger.exception("Listener error, restarting in 10s...")
            time.sleep(10)


def _handle_notification(msg):
    envelope = msg.get("params", {}).get("envelope", {})
    source = envelope.get("source")

    text = None
    sender = None
    group_id = None
    timestamp = envelope.get("timestamp")

    data_message = envelope.get("dataMessage")
    if data_message and data_message.get("message"):
        text = data_message["message"]
        sender = source
        group_id = (data_message.get("groupInfo") or {}).get("groupId")
        if data_message.get("timestamp"):
            timestamp = data_message["timestamp"]

    if not text:
        sync = envelope.get("syncMessage")
        if sync and sync.get("sentMessage"):
            sent = sync["sentMessage"]
            if sent.get("message"):
                text = sent["message"]
                sender = source
                group_info = sent.get("groupInfo") or {}
                group_id = group_info.get("groupId")
                if sent.get("timestamp"):
                    timestamp = sent["timestamp"]

    if not text:
        return

    logger.info("Message: sender=%s group=%s text=%s", sender, group_id, text[:80])
    if timestamp and time.time() - timestamp / 1000 > MAX_MESSAGE_AGE:
        return
    _match_triggers(text, sender, group_id, timestamp)


def _match_triggers(text, sender, group_id, timestamp=None):
    triggers = Trigger.objects.filter(
        trigger_type=Trigger.TriggerType.MESSAGE,
        enabled=True,
        job__enabled=True,
    ).select_related("job").prefetch_related("listen_chats")

    for trigger in triggers:
        if not trigger.pattern:
            continue
        if not re.search(trigger.pattern, text):
            continue

        if trigger.listen_chats.exists():
            chat_ids = set(trigger.listen_chats.values_list("identifier", flat=True))
            if group_id not in chat_ids and sender not in chat_ids:
                continue

        logger.info(
            "Message trigger %d matched for job '%s': %s",
            trigger.id, trigger.job.name, text[:50],
        )
        execute_job(
            trigger.job_id,
            trigger_id=trigger.id,
            trigger_context={
                "sender": sender,
                "message": text,
                "group": group_id,
                "timestamp": timestamp,
            },
        )
