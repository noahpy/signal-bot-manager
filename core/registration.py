"""Register a phone number (incl. landlines via voice call) as the bot's primary account.

Signal's flow, as driven through signal-cli:
  1. ``register --captcha <token>``          -> requests an SMS (required even for landlines)
  2. wait ~60s, ``register --voice [--captcha]`` -> the number gets called, a voice reads a code
  3. ``verify <code> [--pin <pin>]``
  4. optional: ``updateProfile --given-name``, ``setPin``

While a registration is in progress the account exists in signal-cli's config but is not
usable yet, so the listener must not start a jsonRpc process for it. That is signalled via a
persistent KeyValue flag (survives restarts), see ``registration_in_progress()``.
"""

import logging
import re
import subprocess
import threading
import time

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

KV_NAMESPACE = "core.registration"
VOICE_WAIT_SECONDS = 65
_lock = threading.Lock()

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_number(raw):
    """Turn '089 1234567' / '0049 89 ...' / '+49 (89) ...' into E.164 (defaults to +49)."""
    s = re.sub(r"[\s\-/()]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    elif s.startswith("0"):
        s = "+49" + s[1:]
    return s


def normalize_captcha(raw):
    s = (raw or "").strip().strip('"').strip("'")
    return s


def _kv():
    from core.utils import load
    return load(KV_NAMESPACE, "state", None) or {}


def _save(state):
    from core.utils import store
    store(KV_NAMESPACE, "state", state)


def get_state():
    state = _kv()
    if state.get("sms_requested_at"):
        elapsed = time.time() - state["sms_requested_at"]
        state["voice_wait_remaining"] = max(0, int(VOICE_WAIT_SECONDS - elapsed))
    else:
        state["voice_wait_remaining"] = None
    return state


def registration_in_progress():
    try:
        state = _kv()
        return bool(state.get("number")) and state.get("step") != "done"
    except Exception:
        return False


def _run(args, timeout=90):
    cmd = [settings.SIGNAL_CLI_PATH, "--config", str(settings.SIGNAL_CLI_CONFIG), *args]
    # Don't log captcha/pin values.
    safe = []
    for i, a in enumerate(args):
        secret = a.startswith("signalcaptcha://") or (i > 0 and args[i - 1] in ("--pin", "setPin", "--captcha"))
        safe.append("<redacted>" if secret else a)
    logger.info("registration: signal-cli %s", " ".join(safe))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"signal-cli timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"signal-cli not found at {settings.SIGNAL_CLI_PATH}"
    output = "\n".join(x for x in (proc.stdout.strip(), proc.stderr.strip()) if x)
    return proc.returncode == 0, output


def _explain(output):
    low = output.lower()
    hints = []
    if "captcha" in low:
        hints.append(
            "Signal wants a (new) captcha: solve one at "
            "https://signalcaptchas.org/registration/generate.html, copy the 'Open Signal' link "
            "and submit again right away (tokens expire after ~1 minute)."
        )
    if "429" in low or "rate limit" in low:
        hints.append("Rate limited by Signal. Wait (sometimes several hours) before retrying.")
    if "voice" in low and ("sms" in low or "wait" in low):
        hints.append("Signal requires an SMS request first and some waiting time before a voice call.")
    if "pin" in low and "lock" in low:
        hints.append("This number has a registration lock PIN set — enter it in the PIN field.")
    return hints


def _fail(state, output):
    state["error"] = output or "signal-cli failed without output"
    state["hints"] = _explain(output)
    _save(state)
    return state


def request_sms(number, captcha):
    number = normalize_number(number)
    if not E164_RE.match(number):
        return {**_kv(), "error": f"'{number}' is not a valid phone number (expected e.g. +49891234567).", "hints": []}
    with _lock:
        state = {"number": number, "step": "sms_requested", "started_at": timezone.now().isoformat(),
                 "log": []}
        _save(state)  # set the in-progress flag before signal-cli creates the account files
        args = ["-a", number, "register"]
        captcha = normalize_captcha(captcha)
        if captcha:
            args += ["--captcha", captcha]
        ok, out = _run(args)
        state["log"].append({"action": "register (sms)", "ok": ok, "output": out[-2000:]})
        if not ok and "InvalidTransportMode" in out:
            # Landline: Signal created the session but refuses SMS. Voice is allowed right away.
            state.update(sms_requested_at=time.time() - VOICE_WAIT_SECONDS, error=None, hints=[])
            _save(state)
            return state
        if not ok:
            state["step"] = "started"
            return _fail(state, out)
        state.update(sms_requested_at=time.time(), error=None, hints=[])
        _save(state)
        return state


def request_voice(captcha):
    with _lock:
        state = _kv()
        number = state.get("number")
        if not number:
            return {**state, "error": "Request the SMS first.", "hints": []}
        wait = VOICE_WAIT_SECONDS - (time.time() - (state.get("sms_requested_at") or 0))
        if wait > 0:
            return {**state, "error": f"Please wait {int(wait)}s more before requesting the call.", "hints": []}
        args = ["-a", number, "register", "--voice"]
        captcha = normalize_captcha(captcha)
        if captcha:
            args += ["--captcha", captcha]
        ok, out = _run(args)
        state.setdefault("log", []).append({"action": "register --voice", "ok": ok, "output": out[-2000:]})
        if not ok:
            return _fail(state, out)
        state.update(step="voice_requested", voice_requested_at=time.time(), error=None, hints=[])
        _save(state)
        return state


def verify(code, pin="", profile_name="", new_pin=""):
    with _lock:
        state = _kv()
        number = state.get("number")
        if not number:
            return {**state, "error": "No registration in progress.", "hints": []}
        code = re.sub(r"\D", "", code or "")
        if len(code) != 6:
            return {**state, "error": "The code must have 6 digits.", "hints": []}
        args = ["-a", number, "verify", code]
        if pin:
            args += ["--pin", pin.strip()]
        ok, out = _run(args)
        state.setdefault("log", []).append({"action": "verify", "ok": ok, "output": out[-2000:]})
        if not ok:
            return _fail(state, out)

        # Post-registration setup; failures here are reported but don't undo the registration.
        warnings = []
        if profile_name.strip():
            ok2, out2 = _run(["-a", number, "updateProfile", "--given-name", profile_name.strip()])
            state["log"].append({"action": "updateProfile", "ok": ok2, "output": out2[-2000:]})
            if not ok2:
                warnings.append(f"Setting the profile name failed: {out2}")
        if new_pin.strip():
            ok3, out3 = _run(["-a", number, "setPin", new_pin.strip()])
            state["log"].append({"action": "setPin", "ok": ok3, "output": "(output hidden)" if ok3 else out3[-2000:]})
            if not ok3:
                warnings.append(f"Setting the registration lock PIN failed: {out3}")

        from core.models import SignalAccount
        # The newly registered number becomes the bot's account; the listener switches over.
        SignalAccount.objects.exclude(phone_number=number).update(linked=False)
        SignalAccount.objects.update_or_create(
            phone_number=number,
            defaults={"linked": True, "linked_at": timezone.now(), "device_name": "primary (registered)"},
        )
        state.update(step="done", error=None, hints=[], warnings=warnings,
                     finished_at=timezone.now().isoformat())
        _save(state)
        logger.info("Registration of %s completed", number)
        from core import jsonrpc
        if jsonrpc.is_running():
            jsonrpc.stop()  # the listener restarts it for the new account
        return state


def reset():
    """Abort / clear the wizard state. Does not touch signal-cli data."""
    with _lock:
        _save({})
    return _kv()
