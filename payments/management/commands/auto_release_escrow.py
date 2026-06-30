from django.core.management.base import BaseCommand
from django.utils import timezone
from payments.models import EscrowTransaction

class Command(BaseCommand):
    help = 'Auto-release escrow funds after dispute window expires'

    def handle(self, *args, **options):
        now = timezone.now()
        ready = EscrowTransaction.objects.filter(
            status='paid',
            dispute_window_end__lte=now,
            is_auto_release_processed=False  # add a boolean field
        )
        for escrow in ready:
            escrow.status = 'released'
            escrow.is_auto_release_processed = True
            escrow.save()
            self.stdout.write(f"Released escrow {escrow.id}")