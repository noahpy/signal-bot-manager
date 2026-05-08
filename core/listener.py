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

    sync = envelope.get("syncMessage")
    if sync and sync.get("sentMessage"):
        sent = sync["sentMessage"]
        logger.info("Sync sentMessage: dest=%s msg=%s",
                     sent.get("destination") or sent.get("destinationNumber"),
                     (sent.get("message") or "")[:50])

    data_message = envelope.get("dataMessage")
    if not data_message or not data_message.get("message"):
        return

    text = data_message["message"]
    sender = envelope.get("source")
    group_id = (data_message.get("groupInfo") or {}).get("groupId")
    logger.info("Incoming message: sender=%s group=%s text=%s", sender, group_id, text[:50])

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
            trigger_context={"sender": sender, "message": text, "group": group_id},
        )
