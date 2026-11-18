from django.contrib import messages
import base64
import io
import threading

import qrcode
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.executor import execute_job
from core import registration
from core.linking import get_link_state, start_linking
from core.models import Chat, Job, JobExecution, SignalAccount
from core.signal_client import SignalClient, detect_account
from dashboard.forms import JobForm, TriggerFormSet


def index(request):
    jobs = Job.objects.prefetch_related("triggers", "target_chats").all()
    recent_executions = JobExecution.objects.select_related("job")[:10]
    account = SignalAccount.objects.filter(linked=True).first()
    if not account:
        detect_account()
        account = SignalAccount.objects.filter(linked=True).first()
    return render(request, "dashboard/index.html", {
        "jobs": jobs,
        "recent_executions": recent_executions,
        "account": account,
    })


def job_list(request):
    jobs = Job.objects.prefetch_related("triggers", "target_chats").all()
    return render(request, "dashboard/job_list.html", {"jobs": jobs})


def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk)
    executions = job.executions.all()[:20]
    return render(request, "dashboard/job_detail.html", {
        "job": job,
        "executions": executions,
    })


def job_create(request):
    if request.method == "POST":
        form = JobForm(request.POST)
        formset = TriggerFormSet(request.POST, prefix="triggers")
        if form.is_valid() and formset.is_valid():
            job = form.save()
            formset.instance = job
            formset.save()
            return redirect("dashboard:job_detail", pk=job.pk)
    else:
        form = JobForm()
        formset = TriggerFormSet(prefix="triggers")
    return render(request, "dashboard/job_form.html", {
        "form": form,
        "formset": formset,
        "title": "Create Job",
    })


def job_edit(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        formset = TriggerFormSet(request.POST, instance=job, prefix="triggers")
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect("dashboard:job_detail", pk=job.pk)
    else:
        form = JobForm(instance=job)
        formset = TriggerFormSet(instance=job, prefix="triggers")
    return render(request, "dashboard/job_form.html", {
        "form": form,
        "formset": formset,
        "title": f"Edit: {job.name}",
    })


def job_delete(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        job.delete()
        return redirect("dashboard:index")
    return render(request, "dashboard/job_confirm_delete.html", {"job": job})


def job_toggle(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        job.enabled = not job.enabled
        job.save(update_fields=["enabled"])
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/job_toggle.html", {"job": job})
    return redirect("dashboard:job_detail", pk=pk)


def job_run(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.method == "POST":
        execute_job(job.id)
    if request.headers.get("HX-Request"):
        return HttpResponse('<span class="badge">Triggered</span>')
    return redirect("dashboard:job_detail", pk=pk)


def job_logs_partial(request, pk):
    job = get_object_or_404(Job, pk=pk)
    executions = job.executions.all()[:20]
    return render(request, "dashboard/partials/job_logs.html", {
        "executions": executions,
    })


def link_account(request):
    state = get_link_state()
    account = SignalAccount.objects.first()
    return render(request, "dashboard/link.html", {
        "state": state,
        "account": account,
    })


def link_start(request):
    if request.method == "POST":
        device_name = request.POST.get("device_name", "signal-bot")
        start_linking(device_name)
    return redirect("dashboard:link_account")


def link_status(request):
    state = get_link_state()
    qr_data_uri = None
    if state["uri"]:
        img = qrcode.make(state["uri"])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return render(request, "dashboard/partials/link_status.html", {
        "state": state,
        "qr_data_uri": qr_data_uri,
    })


def register_account(request):
    account = SignalAccount.objects.filter(linked=True).first()
    devices, devices_error = None, None
    if account and not registration.registration_in_progress():
        try:
            from core.signal_client import SignalClient
            devices = SignalClient()._call("listDevices", timeout=30)
        except Exception as e:
            devices_error = str(e)
    return render(request, "dashboard/register.html", {
        "state": registration.get_state(),
        "account": account,
        "devices": devices,
        "devices_error": devices_error,
    })


def register_action(request, action):
    if request.method != "POST":
        return redirect("dashboard:register_account")
    p = request.POST
    if action == "sms":
        registration.request_sms(p.get("number", ""), p.get("captcha", ""))
    elif action == "voice":
        registration.request_voice(p.get("captcha", ""), number=p.get("number", ""))
    elif action == "verify":
        registration.verify(p.get("code", ""), pin=p.get("pin", ""),
                            profile_name=p.get("profile_name", ""), new_pin=p.get("new_pin", ""))
    elif action == "reset":
        registration.reset()
    return redirect("dashboard:register_account")


def device_add(request):
    if request.method == "POST":
        uri = request.POST.get("uri", "").strip()
        try:
            from core.signal_client import SignalClient
            SignalClient()._call("addDevice", uri=uri, timeout=60)
            messages.success(request, "Device linked.")
        except Exception as e:
            messages.error(request, f"Linking the device failed: {e}")
    return redirect("dashboard:register_account")


def chat_list(request):
    chats = Chat.objects.all()
    return render(request, "dashboard/chats.html", {"chats": chats})


_sync_state = {"running": False, "errors": []}


def _sync_worker():
    _sync_state["errors"] = []
    client = SignalClient()

    try:
        acct = SignalAccount.objects.filter(linked=True).first()
        if acct and acct.phone_number:
            Chat.objects.update_or_create(
                identifier=acct.phone_number,
                defaults={
                    "chat_type": Chat.ChatType.CONTACT,
                    "name": "Note to Self",
                },
            )
    except Exception as e:
        _sync_state["errors"].append(f"Note to Self: {e}")

    try:
        contacts = client.list_contacts()
        for c in contacts:
            number = c.get("number")
            uuid = c.get("uuid")
            profile = c.get("profile") or {}
            profile_name = " ".join(filter(None, [profile.get("givenName"), profile.get("familyName")])).strip()
            name = profile_name or c.get("name") or c.get("contactName") or c.get("profileName", "")
            identifier = number or uuid
            if not identifier:
                continue
            Chat.objects.update_or_create(
                identifier=identifier,
                defaults={
                    "chat_type": Chat.ChatType.CONTACT,
                    "name": name.strip(),
                },
            )
    except Exception as e:
        _sync_state["errors"].append(f"Contacts: {e}")

    try:
        groups = client.list_groups()
        for g in groups:
            gid = g.get("id") or g.get("groupId")
            if gid:
                Chat.objects.update_or_create(
                    identifier=gid,
                    defaults={
                        "chat_type": Chat.ChatType.GROUP,
                        "name": g.get("name") or "",
                    },
                )
    except Exception as e:
        _sync_state["errors"].append(f"Groups: {e}")

    _sync_state["running"] = False


def chat_sync(request):
    if request.method == "POST" and not _sync_state["running"]:
        _sync_state["running"] = True
        threading.Thread(target=_sync_worker, daemon=True).start()

    if request.headers.get("HX-Request"):
        chats = Chat.objects.all()
        return render(request, "dashboard/partials/chat_list.html", {
            "chats": chats,
            "syncing": _sync_state["running"],
            "errors": _sync_state["errors"],
        })
    return redirect("dashboard:chat_list")
