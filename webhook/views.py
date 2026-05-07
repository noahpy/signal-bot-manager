import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.executor import execute_job
from core.models import Trigger


@csrf_exempt
@require_POST
def webhook_trigger(request, token):
    trigger = get_object_or_404(
        Trigger,
        webhook_token=token,
        trigger_type=Trigger.TriggerType.WEBHOOK,
        enabled=True,
    )
    if not trigger.job.enabled:
        return JsonResponse({"error": "job disabled"}, status=403)

    try:
        payload = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        payload = {}

    execute_job(trigger.job_id, trigger_id=trigger.id, trigger_context={"payload": payload})
    return JsonResponse({"status": "triggered"})
