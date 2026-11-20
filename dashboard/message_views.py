"""Messages page: read the bot's recent chat messages (in-memory only, see core.inbox) and send."""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

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
MAX_FILES = 10
MAX_FILE_BYTES = 20 * 1024 * 1024
# Pillow format -> file extension signal-cli/Signal use to pick the content type.
IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


def _check_image(upload):
    """Return the file extension if the upload is a real image we can send, else raise ValueError."""
    from PIL import Image, UnidentifiedImageError
    if upload.size > MAX_FILE_BYTES:
        raise ValueError(f"{upload.name}: too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB)")
    try:
        with Image.open(upload) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError(f"{upload.name}: not a valid image")
    finally:
        upload.seek(0)
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"{upload.name}: {fmt} is not supported (JPEG, PNG, GIF, WebP)")
    return IMAGE_FORMATS[fmt]


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
        "max_files": MAX_FILES, "max_mb": MAX_FILE_BYTES // (1024 * 1024),
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
    uploads = request.FILES.getlist("images")
    if not text and not uploads:
        flash.error(request, "Write a message or choose an image.")
    elif len(text) > MAX_LENGTH:
        flash.error(request, f"Message is too long (max {MAX_LENGTH} characters).")
    elif len(uploads) > MAX_FILES:
        flash.error(request, f"At most {MAX_FILES} images per message.")
    else:
        # Uploads go to a private temp dir only for the duration of the send, then are deleted.
        tmp = Path(tempfile.mkdtemp(prefix="dashboard-upload-"))
        try:
            paths = []
            for i, up in enumerate(uploads):
                ext = _check_image(up)
                path = tmp / f"image-{i + 1}.{ext}"
                with open(path, "wb") as f:
                    for chunk in up.chunks():
                        f.write(chunk)
                paths.append(str(path))
            SignalClient().send_to_chat(chat, text, attachments=paths or None)
        except ValueError as e:
            flash.error(request, str(e))
        except Exception as e:
            flash.error(request, f"Sending failed: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return redirect("dashboard:message_chat", pk=chat.pk)
