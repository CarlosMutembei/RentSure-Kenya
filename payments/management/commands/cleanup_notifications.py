from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from properties.models import Notification

class Command(BaseCommand):
    help = 'Delete notifications older than X days'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=1)   # keep only last 1 day
        old = Notification.objects.filter(created_at__lt=cutoff)
        count = old.count()
        old.delete()
        self.stdout.write(f"Deleted {count} old notifications")