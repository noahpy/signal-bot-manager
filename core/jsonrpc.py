import json
import logging
import subprocess
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_process = None
_id_counter = 0
_pending = {}
_pending_lock = threading.Lock()
_read_thread = None
_on_notification = None


def start(account, on_notification=None):
    global _process, _read_thread, _on_notification
    _on_notification = on_notification

    cmd = [
        settings.SIGNAL_CLI_PATH,
        "--config", str(settings.SIGNAL_CLI_CONFIG),
        "-a", account,
        "--trust-new-identities", "always",
        "--output=json",
        "jsonRpc",
        "--ignore-avatars",
        "--ignore-stories",
    ]
    logger.info("Starting shared jsonRpc process: %s", " ".join(cmd))
    _process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _read_thread = threading.Thread(target=_reader_loop, daemon=True)
    _read_thread.start()


def is_running():
    return _process is not None and _process.poll() is None


def stop():
    global _process
    if _process and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None


def call(method, timeout=120, **params):
    global _id_counter
    if not is_running():
        raise RuntimeError("jsonRpc process not running")

    with _lock:
        _id_counter += 1
        req_id = _id_counter

    event = threading.Event()
    with _pending_lock:
        _pending[req_id] = {"event": event, "result": None, "error": None}

    request = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params:
        request["params"] = params

    try:
        _process.stdin.write(json.dumps(request) + "\n")
        _process.stdin.flush()
    except (BrokenPipeError, OSError) as e:
        with _pending_lock:
            _pending.pop(req_id, None)
        raise RuntimeError(f"jsonRpc process pipe broken: {e}")

    if not event.wait(timeout=timeout):
        with _pending_lock:
            _pending.pop(req_id, None)
        raise TimeoutError(f"jsonRpc call {method} timed out after {timeout}s")

    with _pending_lock:
        entry = _pending.pop(req_id)

    if entry["error"]:
        raise RuntimeError(entry["error"])
    return entry["result"]


def _reader_loop():
    for line in _process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if "id" in msg and msg["id"] is not None:
            req_id = msg["id"]
            with _pending_lock:
                if req_id in _pending:
                    if "error" in msg:
                        _pending[req_id]["error"] = msg["error"].get("message", str(msg["error"]))
                    else:
                        _pending[req_id]["result"] = msg.get("result")
                    _pending[req_id]["event"].set()
        elif "method" in msg:
            logger.info("jsonRpc notification: method=%s", msg.get("method"))
            if msg.get("method") == "receive" and _on_notification:
                try:
                    _on_notification(msg)
                except Exception:
                    logger.exception("Error handling notification")

    logger.warning("jsonRpc reader loop ended (process exited)")
