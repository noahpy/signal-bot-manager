import json
import logging
import re
import subprocess
import time

from django.conf import settings

from core.executor import execute_job
from core.models import SignalAccount, Trigger

logger = logging.getLogger(__name__)


def listener_loop():
    logger.info("Message listener started")
    while True:
        try:
            _listen()
        except Exception:
            logger.exception("Listener error, restarting in 10s...")
            time.sleep(10)


def _listen():
    acct = SignalAccount.objects.filter(linked=True).first()
    if not acct or not acct.phone_number:
        logger.info("No linked account, waiting...")
        time.sleep(10)
        return

    cmd = [
        settings.SIGNAL_CLI_PATH,
        "--config", str(settings.SIGNAL_CLI_CONFIG),
        "-a", acct.phone_number,
        "--output=json",
        "jsonRpc",
    ]
    logger.info("Starting jsonRpc listener for %s", acct.phone_number)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            _handle_line(line)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _handle_line(line):
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return

    if msg.get("method") != "receive":
        return

    envelope = msg.get("params", {}).get("envelope", {})
    data_message = envelope.get("dataMessage")
    if not data_message or not data_message.get("message"):
        return

    text = data_message["message"]
    sender = envelope.get("source")
    group_id = (data_message.get("groupInfo") or {}).get("groupId")

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
