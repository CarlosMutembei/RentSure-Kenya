from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from payments.models import EscrowTransaction

class Command(BaseCommand):
    help = 'Release units that have not been confirmed within 72 hours of booking'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=72)
        expired = EscrowTransaction.objects.filter(
            status='pending',
            booking_created_at__lte=cutoff,
            auto_released=False
        )
        for escrow in expired:
            unit = escrow.unit
            unit.status = 'available'
            unit.save()
            
            # Calculate penalty if expected_move_in_date is beyond 3 days
            # But penalty logic already computed; we can just apply it
            # Here we simply mark as auto_released
            escrow.status = 'auto_released'
            escrow.auto_released = True
            escrow.save()
            
            self.stdout.write(f"Released unit {unit.id} from booking {escrow.id}")