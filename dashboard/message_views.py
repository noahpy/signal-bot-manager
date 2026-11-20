"""Messages page: read the bot's recent chat messages (in-memory only, see core.inbox) and send."""

from datetime import datetime

from django.conf import settings
from django.contrib import messages as flash
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import inbox, jsonrpc
from core.models import Chat
from core.signal_client import SignalClient

MAX_LENGTH = 4000


def _names():
    """Sender id (number/uuid) -> display name, from the synced contacts."""
    return {c.identifier: c.name for c in Chat.objects.filter(chat_type=Chat.ChatType.CONTACT) if c.name}


def _decorate(msgs):
    names = _names()
    tz = timezone.get_current_timezone()
    for m in msgs:
        m = dict(m)
        m["time"] = datetime.fromtimestamp(m["ts"], tz)
        m["who"] = "Bot" if m["direction"] == "out" else (names.get(m["sender"]) or m["sender_name"] or m["sender"])
        yield m


def _enabled():
    if not settings.MESSAGES_PAGE:
        raise Http404("Messages page disabled (MESSAGES_PAGE=0)")


def message_index(request):
    _enabled()
    summary = inbox.summary()
    tz = timezone.get_current_timezone()
    rows = []
    for c in Chat.objects.all():
        count, last = summary.get(c.identifier, (0, None))
        rows.append({"chat": c, "count": count, "last": datetime.fromtimestamp(last, tz) if last else None})
    rows.sort(key=lambda r: (r["last"] is None, -(r["last"].timestamp() if r["last"] else 0), r["chat"].name.lower()))
    return render(request, "dashboard/messages.html", {"rows": rows, "running": jsonrpc.is_running()})


def message_chat(request, pk):
    _enabled()
    chat = get_object_or_404(Chat, pk=pk)
    return render(request, "dashboard/message_chat.html", {
        "chat": chat, "msgs": list(_decorate(inbox.messages(chat.identifier))),
        "running": jsonrpc.is_running(), "max_length": MAX_LENGTH,
    })


def message_chat_partial(request, pk):
    _enabled()
    chat = get_object_or_404(Chat, pk=pk)
    return render(request, "dashboard/partials/message_list.html", {
        "chat": chat, "msgs": list(_decorate(inbox.messages(chat.identifier)))})


@require_POST
def message_send(request, pk):
    _enabled()
    chat = get_object_or_404(Chat, pk=pk)
    text = (request.POST.get("text") or "").strip()
    if not text:
        flash.error(request, "Message is empty.")
    elif len(text) > MAX_LENGTH:
        flash.error(request, f"Message is too long (max {MAX_LENGTH} characters).")
    else:
        try:
            SignalClient().send_to_chat(chat, text)
        except Exception as e:
            flash.error(request, f"Sending failed: {e}")
    return redirect("dashboard:message_chat", pk=chat.pk)
