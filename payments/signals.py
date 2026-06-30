from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import EscrowTransaction
from properties.models import Notification

@receiver(post_save, sender=EscrowTransaction)
def escrow_status_changed(sender, instance, created, **kwargs):
    # Only when status becomes 'paid' and it's not a new record
    if not created and instance.status == 'paid':
        # Check if a notification already exists for this escrow
        existing = Notification.objects.filter(
            user=instance.landlord,
            link=f"/escrow/status/{instance.id}/"
        ).exists()
        if not existing:
            Notification.objects.create(
                user=instance.landlord,
                title="Escrow Payment Received",
                message=f"Tenant {instance.tenant.username} has paid KES {instance.amount} into escrow for {instance.property.title}. Funds are now held securely.",
                link=f"/escrow/status/{instance.id}/"
            )