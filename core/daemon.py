import logging
import os
import signal
import subprocess
import time

from django.conf import settings

logger = logging.getLogger(__name__)


class DaemonManager:
    def __init__(self):
        self._process = None

    @property
    def socket_path(self):
        return settings.SIGNAL_CLI_SOCKET

    @property
    def config_path(self):
        return str(settings.SIGNAL_CLI_CONFIG)

    def start(self):
        if self.is_running():
            logger.info("signal-cli daemon already running")
            return

        os.makedirs(self.config_path, exist_ok=True)

        cmd = [
            settings.SIGNAL_CLI_PATH,
            "--config", self.config_path,
            "daemon",
            "--socket", self.socket_path,
            "--no-receive-stdout",
        ]
        logger.info("Starting signal-cli daemon: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(30):
            time.sleep(0.5)
            if os.path.exists(self.socket_path):
                logger.info("signal-cli daemon started (pid=%d)", self._process.pid)
                return
        raise RuntimeError("signal-cli daemon did not create socket within 15 seconds")

    def stop(self):
        if self._process and self._process.poll() is None:
            logger.info("Stopping signal-cli daemon (pid=%d)", self._process.pid)
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def is_running(self):
        if self._process is None:
            return False
        return self._process.poll() is None

    def health_check(self):
        if not self.is_running():
            return False
        try:
            from core.signal_client import SignalClient
            client = SignalClient(self.socket_path)
            client.get_account()
            return True
        except Exception:
            return False

    def ensure_running(self):
        if not self.is_running():
            logger.warning("signal-cli daemon not running, restarting...")
            self.start()
