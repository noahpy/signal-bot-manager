import re
import subprocess

from django.conf import settings


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

    def send(self, recipient, message, attachments=None):
        params = {"recipient": [recipient], "message": message}
        if attachments:
            params["attachments"] = attachments
        return self._call("send", timeout=30, **params)

    def send_group(self, group_id, message, attachments=None):
        params = {"groupId": group_id, "message": message}
        if attachments:
            params["attachments"] = attachments
        return self._call("send", timeout=30, **params)

    def send_to_chat(self, chat, message, attachments=None):
        from core.models import Chat
        if chat.chat_type == Chat.ChatType.GROUP:
            return self.send_group(chat.identifier, message, attachments)
        return self.send(chat.identifier, message, attachments)

    def list_groups(self):
        try:
            result = self._call("listGroups", timeout=120)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def list_contacts(self):
        try:
            result = self._call("listContacts", timeout=60)
            return result if isinstance(result, list) else []
        except Exception:
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
            params["attachments"] = attachments
        return self._call("send", timeout=30, **params)

    def send_group_with_mention(self, group_id, message, mentions, attachments=None):
        params = {"groupId": group_id, "message": message, "mention": mentions}
        if attachments:
            params["attachments"] = attachments
        return self._call("send", timeout=30, **params)

    def send_poll(self, recipient, question, options, multi_vote=False):
        params = {
            "recipient": [recipient],
            "pollMessage": {"question": question, "options": options, "multiVote": multi_vote},
        }
        return self._call("send", timeout=30, **params)

    def send_group_poll(self, group_id, question, options, multi_vote=False):
        params = {
            "groupId": group_id,
            "pollMessage": {"question": question, "options": options, "multiVote": multi_vote},
        }
        return self._call("send", timeout=30, **params)
