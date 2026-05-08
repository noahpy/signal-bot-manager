import json
import logging
import os
import re
import socket
import time

from django.conf import settings

from core.executor import execute_job
from core.models import Trigger

logger = logging.getLogger(__name__)


def listener_loop():
    logger.info("Message listener started")
    while True:
        try:
            _listen()
        except Exception:
            logger.exception("Listener error, reconnecting in 5s...")
            time.sleep(5)


def _listen():
    while not os.path.exists(settings.SIGNAL_CLI_SOCKET):
        logger.info("Waiting for daemon socket...")
        time.sleep(2)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(settings.SIGNAL_CLI_SOCKET)
    logger.info("Connected to signal-cli daemon socket")

    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                _handle_line(line.decode())
    finally:
        sock.close()


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
