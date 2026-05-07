from django.core.management.base import BaseCommand

from core.daemon import DaemonManager


class Command(BaseCommand):
    help = "Start the signal-cli daemon"

    def handle(self, *args, **options):
        dm = DaemonManager()
        dm.start()
        self.stdout.write(self.style.SUCCESS("signal-cli daemon started"))
        try:
            dm._process.wait()
        except KeyboardInterrupt:
            dm.stop()
