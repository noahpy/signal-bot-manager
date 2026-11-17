import os
import signal
import sys
import threading
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signalbot.settings")

import django
django.setup()


def run_django():
    from django.core.management import call_command
    from django.conf import settings
    call_command("runserver", settings.BIND_ADDRESS, use_reloader=False)


def run_scheduler():
    from core.scheduler import scheduler_loop
    scheduler_loop()


def run_listener():
    from core.listener import listener_loop
    listener_loop()


def run_cleanup():
    from core.cleanup import cleanup_loop
    cleanup_loop()


def run_alerts():
    from core.alerts import alert_loop
    alert_loop()


def main():
    import logging
    from core.alerts import AlertHandler
    logging.getLogger().addHandler(AlertHandler())

    threads = []

    def shutdown(signum, frame):
        from core import jsonrpc
        jsonrpc.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for name, target in [
        ("django", run_django),
        ("scheduler", run_scheduler),
        ("listener", run_listener),
        ("cleanup", run_cleanup),
        ("alerts", run_alerts),
    ]:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        print(f"Started {name}")
        threads.append(t)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
