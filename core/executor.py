import importlib.util
import io
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from core.models import Chat, Job, JobExecution, Trigger
from core.signal_client import SignalClient

logger = logging.getLogger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=4)


@dataclass
class JobContext:
    signal: SignalClient
    target_chats: list
    config: dict
    trigger_context: dict
    log: logging.Logger


def execute_job(job_id, trigger_id=None, trigger_context=None):
    _thread_pool.submit(_run_job, job_id, trigger_id, trigger_context or {})


def execute_job_sync(job_id, trigger_id=None, trigger_context=None):
    _run_job(job_id, trigger_id, trigger_context or {})


def _run_job(job_id, trigger_id, trigger_context):
    job = Job.objects.get(id=job_id)
    trigger = Trigger.objects.get(id=trigger_id) if trigger_id else None
    execution = JobExecution.objects.create(
        job=job,
        trigger=trigger,
        trigger_context=trigger_context,
        status=JobExecution.Status.RUNNING,
    )

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    job_logger = logging.getLogger(f"job.{job_id}.{execution.id}")
    job_logger.addHandler(handler)
    job_logger.setLevel(logging.DEBUG)

    try:
        if job.job_type == Job.JobType.SIMPLE:
            _execute_simple(job, execution, job_logger)
        else:
            _execute_script(job, execution, job_logger)
        execution.status = JobExecution.Status.SUCCESS
    except Exception as e:
        execution.status = JobExecution.Status.FAILED
        execution.error_message = traceback.format_exc()
        job_logger.error("Job failed: %s", e)
    finally:
        execution.finished_at = timezone.now()
        execution.duration_ms = int(
            (execution.finished_at - execution.started_at).total_seconds() * 1000
        )
        execution.log_output = log_stream.getvalue()
        execution.save()
        job_logger.removeHandler(handler)


def _resolve_chats(job, trigger_context):
    chats = list(job.target_chats.all())
    if job.reply_to_trigger_chat and trigger_context:
        group_id = trigger_context.get("group")
        sender = trigger_context.get("sender")
        identifier = group_id or sender
        if identifier:
            try:
                trigger_chat = Chat.objects.get(identifier=identifier)
            except Chat.DoesNotExist:
                chat_type = Chat.ChatType.GROUP if group_id else Chat.ChatType.CONTACT
                trigger_chat = Chat.objects.create(
                    identifier=identifier, chat_type=chat_type, name=""
                )
            if trigger_chat not in chats:
                chats.insert(0, trigger_chat)
    return chats


def _execute_simple(job, execution, job_logger):
    client = SignalClient()
    message = job.message_template
    chats = _resolve_chats(job, execution.trigger_context)
    job_logger.info("Sending message to %d chat(s)", len(chats))
    for chat in chats:
        client.send_to_chat(chat, message)
        job_logger.info("Sent to %s", chat)


def _execute_script(job, execution, job_logger):
    script_file = settings.SCRIPTS_DIR / job.script_path
    if not script_file.exists():
        raise FileNotFoundError(f"Script not found: {script_file}")

    ctx = JobContext(
        signal=SignalClient(),
        target_chats=_resolve_chats(job, execution.trigger_context),
        config=job.config_json,
        trigger_context=execution.trigger_context,
        log=job_logger,
    )

    spec = importlib.util.spec_from_file_location("job_script", str(script_file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise AttributeError(f"Script {job.script_path} has no run(ctx) function")

    module.run(ctx)
