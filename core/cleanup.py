"""Daily cleanup so the server keeps no Signal messages or attachments around."""

import logging
import time

from django.conf import settings
from django.db import connection
from django.utils import timezone

from core.models import JobExecution

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL = 24 * 60 * 60
MAX_AGE = 24 * 60 * 60
# signal-cli caches downloaded media here; data/ holds the account keys and
# must never be touched.
MEDIA_DIRS = ["attachments", "stickers"]


def cleanup_loop():
    logger.info("Cleanup loop started")
    while True:
        try:
            run_cleanup()
        except Exception:
            logger.exception("Cleanup failed")
        try:
            # Daily chat/contact sync keeps member names (Signal profiles) current.
            from core import jsonrpc
            if jsonrpc.is_running():
                from dashboard.views import _sync_worker
                _sync_worker()
        except Exception:
            logger.exception("Daily chat sync failed")
        time.sleep(CLEANUP_INTERVAL)


def run_cleanup():
    files = _delete_old_media()
    rows = _wipe_messages()
    logger.info("Cleanup: deleted %d media file(s), wiped %d message(s)", files, rows)


def _delete_old_media():
    cutoff = time.time() - MAX_AGE
    deleted = 0
    for name in MEDIA_DIRS:
        root = settings.SIGNAL_CLI_CONFIG / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
    return deleted


def _wipe_messages():
    # The executor clears trigger_context when a job finishes; this catches
    # anything left behind by a crash mid-job.
    cutoff = timezone.now() - timezone.timedelta(seconds=MAX_AGE)
    rows = (
        JobExecution.objects.filter(started_at__lt=cutoff)
        .exclude(trigger_context={})
        .update(trigger_context={})
    )
    # SQLite keeps deleted text in free pages until vacuumed.
    with connection.cursor() as cursor:
        cursor.execute("VACUUM")
    return rows
