"""JSON API for signal-bot-reminder-generator.

Auth: ``Authorization: Bearer <REMINDER_API_TOKEN>``. Disabled while the token is unset.
"""

import functools
import hmac
import json
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from core import reminders
from core.executor import execute_job
from core.models import Chat, Job, JobExecution, SignalAccount, Trigger

MANAGED_BY = "reminder-generator"
RUNNER_SCRIPT = "reminder_runner.py"


def runner_cron(spec):
    """UTC cron that fires at spec.send_time local time in both standard and DST offsets.

    The runner dedupes per day and checks the local time itself, so the extra run is a no-op.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(spec["timezone"])
    hh, mm = map(int, spec["send_time"].split(":"))
    times = set()
    for month in (1, 7):
        local = datetime(2026, month, 1, hh, mm, tzinfo=tz)
        utc = local.astimezone(ZoneInfo("UTC"))
        times.add((utc.hour, utc.minute))
    minutes = {m for _, m in times}
    if len(minutes) == 1:
        return f"{minutes.pop()} {','.join(str(h) for h in sorted({h for h, _ in times}))} * * *"
    return "*/15 * * * *"  # odd half-hour offset zones: fall back to polling


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


def api_view(methods):
    def deco(fn):
        @csrf_exempt
        @functools.wraps(fn)
        def wrapper(request, *args, **kwargs):
            token = settings.REMINDER_API_TOKEN
            if not token:
                return _err("API disabled (REMINDER_API_TOKEN not set)", 403)
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:].encode(), token.encode()):
                return _err("unauthorized", 401)
            if request.method not in methods:
                return _err("method not allowed", 405)
            body = {}
            if request.body:
                try:
                    body = json.loads(request.body)
                except json.JSONDecodeError:
                    return _err("invalid JSON")
            try:
                return fn(request, body, *args, **kwargs)
            except reminders.SpecError as e:
                return _err(f"invalid spec: {e}")
        return wrapper
    return deco


def _signal():
    from core.signal_client import SignalClient
    return SignalClient()


@api_view(["GET"])
def status(request, body):
    acct = SignalAccount.objects.filter(linked=True).first()
    from core import jsonrpc
    return JsonResponse({
        "account": acct.phone_number if acct else None,
        "signal_running": jsonrpc.is_running(),
    })


@api_view(["GET"])
def groups(request, body):
    data = [{"id": c.identifier, "name": c.name} for c in Chat.objects.filter(chat_type=Chat.ChatType.GROUP).order_by("name")]
    return JsonResponse({"groups": data})


@api_view(["POST"])
def groups_sync(request, body):
    from dashboard.views import _sync_worker
    import threading
    threading.Thread(target=_sync_worker, daemon=True).start()
    return JsonResponse({"status": "sync started"})


@api_view(["GET"])
def group_members(request, body):
    group_id = request.GET.get("id", "")
    try:
        chat = Chat.objects.get(identifier=group_id, chat_type=Chat.ChatType.GROUP)
    except Chat.DoesNotExist:
        return _err("unknown group", 404)
    from core.utils import resolve_group_members
    try:
        members = resolve_group_members(_signal(), chat)
    except Exception as e:
        return _err(f"could not load members: {e}", 503)
    own = SignalAccount.objects.filter(linked=True).values_list("phone_number", flat=True).first()
    members = [
        {"uuid": m.get("uuid"), "number": m.get("number"), "name": m.get("name") or ""}
        for m in members if not (own and m.get("number") == own)
    ]
    members.sort(key=lambda m: (m["name"] or "~").lower())
    return JsonResponse({"group": {"id": chat.identifier, "name": chat.name}, "members": members})


def _job_json(job):
    last = job.executions.first()
    return {
        "external_id": job.external_id,
        "job_id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "group_id": (job.target_chats.first() or Chat(identifier="")).identifier,
        "spec": {k: v for k, v in job.config_json.items() if k != "external_id"},
        "last_execution": {
            "status": last.status,
            "started_at": last.started_at.isoformat(),
            "error": last.error_message[-2000:],
            "log": last.log_output[-4000:],
        } if last else None,
    }


def _get_job(external_id):
    return Job.objects.filter(managed_by=MANAGED_BY, external_id=external_id).first()


@api_view(["GET"])
def reminder_list(request, body):
    jobs = Job.objects.filter(managed_by=MANAGED_BY).prefetch_related("target_chats").order_by("name")
    return JsonResponse({"reminders": [_job_json(j) for j in jobs]})


@api_view(["GET", "PUT", "DELETE"])
def reminder_detail(request, body, external_id):
    job = _get_job(external_id)
    if request.method == "GET":
        if not job:
            return _err("not found", 404)
        return JsonResponse(_job_json(job))
    if request.method == "DELETE":
        if job:
            job.delete()
        return JsonResponse({"status": "deleted"})

    # PUT: upsert. body = {"group_id", "spec", "enabled", "name"?}
    spec = reminders.validate(body.get("spec"), settings.REMINDER_DEFAULT_TZ)
    try:
        chat = Chat.objects.get(identifier=body.get("group_id", ""))
    except Chat.DoesNotExist:
        return _err("unknown group_id (sync chats first?)", 404)
    with transaction.atomic():
        if not job:
            job = Job(managed_by=MANAGED_BY, external_id=external_id, job_type=Job.JobType.SCRIPT)
        job.name = (body.get("name") or spec["title"])[:200]
        job.description = f"Managed by signal-bot-reminder-generator ({external_id}). Edit it there."
        job.script_path = RUNNER_SCRIPT
        job.config_json = {**spec, "external_id": external_id}
        job.enabled = bool(body.get("enabled", True))
        job.save()
        job.target_chats.set([chat])
        cron = runner_cron(spec)
        trig = job.triggers.filter(trigger_type=Trigger.TriggerType.CRON).first()
        if not trig:
            Trigger.objects.create(job=job, trigger_type=Trigger.TriggerType.CRON, cron_expression=cron)
        elif trig.cron_expression != cron or not trig.enabled:
            trig.cron_expression, trig.enabled = cron, True
            trig.save()
    return JsonResponse(_job_json(job))


@api_view(["POST"])
def preview(request, body):
    """Dry run: {"spec": {...}, "from": "YYYY-MM-DD", "days": 60} -> reminders that would be sent."""
    spec = reminders.validate(body.get("spec"), settings.REMINDER_DEFAULT_TZ)
    start = date.fromisoformat(body["from"]) if body.get("from") else reminders.local_now(spec).date()
    days = max(1, min(int(body.get("days") or 60), 800))
    items = []
    for remind_day, occ, people in reminders.upcoming(spec, start, days):
        text, _, _ = reminders.render(spec, occ, people, remind_day, None)
        items.append({
            "send_on": remind_day.isoformat(),
            "send_time": spec["send_time"],
            "occurrence": occ.isoformat(),
            "people": [p.get("name") or p.get("uuid") for p in people],
            "text": text,
        })
    return JsonResponse({"spec": spec, "items": items})


@api_view(["POST"])
def reminder_run(request, body, external_id):
    job = _get_job(external_id)
    if not job:
        return _err("not found", 404)
    execute_job(job.id, trigger_context={"payload": {"force": True}})
    return JsonResponse({"status": "started"})


@api_view(["GET"])
def reminder_executions(request, body, external_id):
    job = _get_job(external_id)
    if not job:
        return _err("not found", 404)
    ex = JobExecution.objects.filter(job=job)[:20]
    return JsonResponse({"executions": [
        {"status": e.status, "started_at": e.started_at.isoformat(), "duration_ms": e.duration_ms,
         "log": e.log_output[-4000:], "error": e.error_message[-2000:]} for e in ex
    ]})
