import logging
import re
import time

from core.executor import execute_job
from core.models import SignalAccount, Trigger

logger = logging.getLogger(__name__)


def listener_loop():
    logger.info("Message listener started")
    while True:
        try:
            acct = SignalAccount.objects.filter(linked=True).first()
            if not acct or not acct.phone_number:
                from core.signal_client import detect_account
                phone = detect_account()
                if not phone:
                    logger.info("No linked account, waiting...")
                    time.sleep(10)
                    continue

            from core import jsonrpc
            if not jsonrpc.is_running():
                logger.info("Starting shared jsonRpc process for %s", acct.phone_number)
                jsonrpc.start(acct.phone_number, on_notification=_handle_notification)

            while jsonrpc.is_running():
                time.sleep(1)

            logger.warning("jsonRpc process died, restarting in 5s...")
            time.sleep(5)
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
