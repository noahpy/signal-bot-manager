import logging
import subprocess
import threading

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_link_state = {
    "active": False,
    "uri": None,
    "error": None,
    "success": False,
    "thread": None,
}


def get_link_state():
    return {
        "active": _link_state["active"],
        "uri": _link_state["uri"],
        "error": _link_state["error"],
        "success": _link_state["success"],
    }


def start_linking(device_name="signal-bot"):
    if _link_state["active"]:
        return

    _link_state.update(active=True, uri=None, error=None, success=False)

    def _link_worker():
        try:
            cmd = [
                settings.SIGNAL_CLI_PATH,
                "--config", str(settings.SIGNAL_CLI_CONFIG),
                "link",
                "-n", device_name,
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("tsdevice:"):
                    _link_state["uri"] = line
                    break

            proc.wait(timeout=120)

            if proc.returncode == 0:
                _link_state["success"] = True
                _save_account_from_link()
            else:
                stderr = proc.stderr.read()
                _link_state["error"] = stderr or f"signal-cli exited with code {proc.returncode}"
        except subprocess.TimeoutExpired:
            proc.kill()
            _link_state["error"] = "Linking timed out (120s)"
        except Exception as e:
            _link_state["error"] = str(e)
        finally:
            _link_state["active"] = False

    t = threading.Thread(target=_link_worker, daemon=True)
    _link_state["thread"] = t
    t.start()


def _save_account_from_link():
    try:
        from core.models import SignalAccount
        result = subprocess.run(
            [settings.SIGNAL_CLI_PATH, "--config", str(settings.SIGNAL_CLI_CONFIG), "listAccounts"],
            capture_output=True, text=True,
        )
        phone = result.stdout.strip().split("\n")[-1].strip() if result.stdout.strip() else ""
        SignalAccount.objects.update_or_create(
            defaults={
                "phone_number": phone,
                "linked": True,
                "linked_at": timezone.now(),
            },
        )
    except Exception as e:
        logger.error("Failed to save account after linking: %s", e)
