from django.core.management.base import BaseCommand

from core.scheduler import scheduler_loop


class Command(BaseCommand):
    help = "Run the cron job scheduler"

    def handle(self, *args, **options):
        self.stdout.write("Starting scheduler...")
        scheduler_loop()
