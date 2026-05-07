import json
import socket

from django.conf import settings


class SignalClientError(Exception):
    pass


class SignalClient:
    def __init__(self, socket_path=None):
        self._socket_path = socket_path or settings.SIGNAL_CLI_SOCKET
        self._id_counter = 0

    def _call(self, method, **params):
        self._id_counter += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._id_counter,
        }
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            sock.sendall(json.dumps(request).encode() + b"\n")
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            response = json.loads(data.decode().strip())
            if "error" in response:
                raise SignalClientError(response["error"].get("message", str(response["error"])))
            return response.get("result")
        finally:
            sock.close()

    def send(self, recipient, message, attachments=None):
        params = {"recipient": [recipient], "message": message}
        if attachments:
            params["attachments"] = attachments
        return self._call("send", **params)

    def send_group(self, group_id, message, attachments=None):
        params = {"groupId": group_id, "message": message}
        if attachments:
            params["attachments"] = attachments
        return self._call("send", **params)

    def send_to_chat(self, chat, message, attachments=None):
        from core.models import Chat
        if chat.chat_type == Chat.ChatType.GROUP:
            return self.send_group(chat.identifier, message, attachments)
        return self.send(chat.identifier, message, attachments)

    def list_groups(self):
        return self._call("listGroups") or []

    def list_contacts(self):
        return self._call("listContacts") or []

    def get_account(self):
        return self._call("listAccounts")
