import multiprocessing
import os
import signal
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signalbot.settings")


def _setup_django():
    import django
    django.setup()


def run_django():
    _setup_django()
    from django.core.management import call_command
    call_command("runserver", "0.0.0.0:8000", use_reloader=False)


def run_scheduler():
    _setup_django()
    from core.scheduler import scheduler_loop
    scheduler_loop()


def run_listener():
    _setup_django()
    from core.listener import listener_loop
    listener_loop()


def run_daemon():
    _setup_django()
    from core.daemon import DaemonManager
    dm = DaemonManager()
    dm.start()
    dm._process.wait()


def _wait_for_socket(path, timeout=30):
    import time
    for _ in range(timeout * 2):
        if os.path.exists(path):
            return True
        time.sleep(0.5)
    return False


def main():
    processes = []

    def shutdown(signum, frame):
        for p in processes:
            if p.is_alive():
                p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    _setup_django()
    from django.conf import settings
    socket_path = settings.SIGNAL_CLI_SOCKET

    # Start daemon first and wait for socket
    daemon_proc = multiprocessing.Process(target=run_daemon, name="daemon", daemon=True)
    daemon_proc.start()
    print(f"Started daemon (pid={daemon_proc.pid})")
    processes.append(daemon_proc)

    if not _wait_for_socket(socket_path):
        print("ERROR: signal-cli daemon did not create socket in time", file=sys.stderr)
        sys.exit(1)
    print("Daemon socket ready")

    # Now start the rest
    for name, target in [
        ("django", run_django),
        ("scheduler", run_scheduler),
        ("listener", run_listener),
    ]:
        p = multiprocessing.Process(target=target, name=name, daemon=True)
        p.start()
        print(f"Started {name} (pid={p.pid})")
        processes.append(p)

    for p in processes:
        p.join()


if __name__ == "__main__":
    main()
