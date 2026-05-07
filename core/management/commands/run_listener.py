from django.core.management.base import BaseCommand

from core.listener import listener_loop


class Command(BaseCommand):
    help = "Run the incoming message listener"

    def handle(self, *args, **options):
        self.stdout.write("Starting message listener...")
        listener_loop()
