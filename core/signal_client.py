import json
import subprocess

from django.conf import settings


class SignalClientError(Exception):
    pass


class SignalClient:
    def __init__(self, account=None):
        self._account = account

    @property
    def account(self):
        if self._account:
            return self._account
        from core.models import SignalAccount
        acct = SignalAccount.objects.filter(linked=True).first()
        if acct and acct.phone_number:
            return acct.phone_number
        return self._detect_account()

    def _detect_account(self):
        import re
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

    def _run(self, *args, timeout=30, json_output=True):
        cmd = [settings.SIGNAL_CLI_PATH, "--config", str(settings.SIGNAL_CLI_CONFIG)]
        acct = self.account
        if acct:
            cmd += ["-a", acct]
        if json_output:
            cmd += ["--output=json"]
        cmd += list(args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise SignalClientError(result.stderr.strip() or f"signal-cli exited with code {result.returncode}")

        if not json_output or not result.stdout.strip():
            return result.stdout.strip()

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout.strip()

    def send(self, recipient, message, attachments=None):
        args = ["send", "-m", message, recipient]
        if attachments:
            for a in attachments:
                args += ["-a", a]
        return self._run(*args, timeout=30)

    def send_group(self, group_id, message, attachments=None):
        args = ["send", "-m", message, "-g", group_id]
        if attachments:
            for a in attachments:
                args += ["-a", a]
        return self._run(*args, timeout=30)

    def send_to_chat(self, chat, message, attachments=None):
        from core.models import Chat
        if chat.chat_type == Chat.ChatType.GROUP:
            return self.send_group(chat.identifier, message, attachments)
        return self.send(chat.identifier, message, attachments)

    def list_groups(self):
        try:
            result = self._run("listGroups", timeout=120)
        except subprocess.TimeoutExpired:
            return []
        return result if isinstance(result, list) else []

    def list_contacts(self):
        try:
            result = self._run("listContacts", timeout=60)
        except subprocess.TimeoutExpired:
            return []
        return result if isinstance(result, list) else []

    def list_accounts(self):
        return self._run("listAccounts", timeout=15)
