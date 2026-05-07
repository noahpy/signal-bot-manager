import logging
import time

from croniter import croniter
from django.utils import timezone

from core.executor import execute_job
from core.models import Trigger

logger = logging.getLogger(__name__)


def scheduler_loop():
    logger.info("Scheduler started")
    while True:
        try:
            _tick()
        except Exception:
            logger.exception("Scheduler tick error")
        time.sleep(30)


def _tick():
    now = timezone.now()
    triggers = Trigger.objects.filter(
        trigger_type=Trigger.TriggerType.CRON,
        enabled=True,
        job__enabled=True,
    ).select_related("job")

    for trigger in triggers:
        if not trigger.cron_expression:
            continue
        try:
            if _should_fire(trigger, now):
                logger.info("Firing cron trigger %d for job '%s'", trigger.id, trigger.job.name)
                trigger.last_fired_at = now
                trigger.save(update_fields=["last_fired_at"])
                execute_job(trigger.job_id, trigger_id=trigger.id)
        except Exception:
            logger.exception("Error evaluating trigger %d", trigger.id)


def _should_fire(trigger, now):
    base_time = trigger.last_fired_at or now - timezone.timedelta(minutes=1)
    cron = croniter(trigger.cron_expression, base_time)
    next_fire = cron.get_next(timezone.datetime)
    if next_fire.tzinfo is None:
        next_fire = timezone.make_aware(next_fire)
    return next_fire <= now
