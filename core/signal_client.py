import logging
import re
import subprocess

from django.conf import settings

logger = logging.getLogger(__name__)


class SignalClientError(Exception):
    pass


def detect_account():
    try:
        result = subprocess.run(
            [settings.SIGNAL_CLI_PATH, "--config", str(settings.SIGNAL_CLI_CONFIG), "listAccounts"],
            capture_output=True, text=True, timeout=15,
        )
        match = re.search(r"(\+\d+)", result.stdout)
        if match:
            phone = match.group(1)
            from core.models import SignalAccount
            from django.utils import timezone
            SignalAccount.objects.update_or_create(
                phone_number=phone,
                defaults={"linked": True, "linked_at": timezone.now()},
            )
            return phone
    except Exception:
        pass
    return None


class SignalClient:
    def _call(self, method, timeout=120, **params):
        from core import jsonrpc
        if not jsonrpc.is_running():
            raise SignalClientError("signal-cli jsonRpc process not running")
        return jsonrpc.call(method, timeout=timeout, **params)

    def send(self, recipient, message, attachments=None, notify_self=False):
        params = {"recipient": [recipient], "message": message}
        if attachments:
            params["attachment"] = attachments
        if notify_self:
            params["notifySelf"] = True
        return self._call("send", timeout=30, **params)

    def send_group(self, group_id, message, attachments=None, notify_self=False):
        params = {"groupId": group_id, "message": message}
        if attachments:
            params["attachment"] = attachments
        if notify_self:
            params["notifySelf"] = True
        return self._call("send", timeout=30, **params)

    def send_note_to_self(self, message, attachments=None):
        params = {"noteToSelf": True, "message": message}
        if attachments:
            params["attachment"] = attachments
        return self._call("send", timeout=30, **params)

    def send_to_chat(self, chat, message, attachments=None, notify_self=False):
        from core.models import Chat
        if chat.chat_type == Chat.ChatType.GROUP:
            return self.send_group(chat.identifier, message, attachments, notify_self)
        return self.send(chat.identifier, message, attachments, notify_self)

    def list_groups(self):
        try:
            result = self._call("listGroups", timeout=120)
            return result if isinstance(result, list) else []
        except Exception:
            logger.warning("listGroups failed, returning no groups", exc_info=True)
            return []

    def list_contacts(self, detailed=False):
        """With detailed=True signal-cli also fetches missing profiles (names) from the server."""
        params = {"allRecipients": True, "detailed": True} if detailed else {}
        try:
            result = self._call("listContacts", timeout=180 if detailed else 60, **params)
            return result if isinstance(result, list) else []
        except Exception:
            logger.warning("listContacts failed, returning no contacts", exc_info=True)
            return []

    def get_group_members(self, group_id):
        groups = self.list_groups()
        for g in groups:
            gid = g.get("id") or g.get("groupId")
            if gid == group_id:
                return g.get("members", [])
        return []

    def send_with_mention(self, recipient, message, mentions, attachments=None):
        params = {"recipient": [recipient], "message": message, "mention": mentions}
        if attachments:
            params["attachment"] = attachments
        return self._call("send", timeout=30, **params)

    def send_group_with_mention(self, group_id, message, mentions, attachments=None):
        params = {"groupId": group_id, "message": message, "mention": mentions}
        if attachments:
            params["attachment"] = attachments
        return self._call("send", timeout=30, **params)

    def send_poll(self, recipient, question, options, no_multi=False):
        params = {
            "recipient": [recipient],
            "question": question,
            "option": options,
        }
        if no_multi:
            params["noMulti"] = True
        return self._call("sendPollCreate", timeout=30, **params)

    def send_group_poll(self, group_id, question, options, no_multi=False):
        params = {
            "groupId": group_id,
            "question": question,
            "option": options,
        }
        if no_multi:
            params["noMulti"] = True
        return self._call("sendPollCreate", timeout=30, **params)

    def pin_message(self, recipient, target_author, target_timestamp, pin_duration=-1):
        return self._call("sendPinMessage", timeout=30,
            recipient=[recipient],
            targetAuthor=target_author,
            targetTimestamp=target_timestamp,
            pinDuration=pin_duration,
        )

    def pin_group_message(self, group_id, target_author, target_timestamp, pin_duration=-1):
        return self._call("sendPinMessage", timeout=30,
            groupId=group_id,
            targetAuthor=target_author,
            targetTimestamp=target_timestamp,
            pinDuration=pin_duration,
        )

    def unpin_message(self, recipient, target_author, target_timestamp):
        return self._call("sendUnpinMessage", timeout=30,
            recipient=[recipient],
            targetAuthor=target_author,
            targetTimestamp=target_timestamp,
        )

    def unpin_group_message(self, group_id, target_author, target_timestamp):
        return self._call("sendUnpinMessage", timeout=30,
            groupId=group_id,
            targetAuthor=target_author,
            targetTimestamp=target_timestamp,
        )

    def send_quote(self, recipient, message, quote_timestamp, quote_author, attachments=None):
        params = {
            "recipient": [recipient],
            "message": message,
            "quoteTimestamp": quote_timestamp,
            "quoteAuthor": quote_author,
        }
        if attachments:
            params["attachment"] = attachments
        return self._call("send", timeout=30, **params)

    def send_group_quote(self, group_id, message, quote_timestamp, quote_author, attachments=None):
        params = {
            "groupId": group_id,
            "message": message,
            "quoteTimestamp": quote_timestamp,
            "quoteAuthor": quote_author,
        }
        if attachments:
            params["attachment"] = attachments
        return self._call("send", timeout=30, **params)
