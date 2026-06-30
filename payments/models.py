from django.db import models
from django.conf import settings
from datetime import timedelta
from django.utils import timezone

class Transaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    property = models.ForeignKey('properties.Property', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mpesa_receipt = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=[('pending','Pending'), ('completed','Completed'), ('failed','Failed')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
class EscrowTransaction(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Payment Pending'),
        ('paid', 'Payment Received (Held)'),
        ('released', 'Released to Landlord'),
        ('refunded', 'Refunded to Tenant'),
        ('disputed', 'Disputed'),
        ('auto_released', 'Auto‑Released (No Move‑in)'),
    )

    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='escrow_tenant'
    )
    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='escrow_landlord'
    )
    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE)
    unit = models.ForeignKey('properties.Unit', on_delete=models.SET_NULL, null=True, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mpesa_receipt = models.CharField(max_length=50, blank=True)

    checkout_request_id = models.CharField(max_length=100, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    move_in_date = models.DateField(null=True, blank=True)
    dispute_window_end = models.DateTimeField(null=True, blank=True)

    # ========== 72‑HOUR HOLD FIELDS ==========
    penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Penalty deducted from escrow if booking expires without move‑in"
    )
    penalty_applied = models.BooleanField(
        default=False,
        help_text="Whether the penalty has been deducted"
    )
    auto_released = models.BooleanField(
        default=False,
        help_text="Whether the booking was auto‑released after 72h without move‑in"
    )

    # ========== DISPUTE / REFUND FIELDS ==========
    dispute_reason = models.TextField(blank=True, null=True)
    dispute_resolved = models.BooleanField(default=False)
    dispute_resolution_notes = models.TextField(
        blank=True, null=True,
        help_text="Admin notes for refund or dispute resolution"
    )

    # ========== METHODS ==========
    def start_dispute_window(self):
        self.dispute_window_end = timezone.now() + timedelta(hours=72)
        self.save()

    def remaining_dispute_seconds(self):
        if self.dispute_window_end:
            delta = self.dispute_window_end - timezone.now()
            return max(0, delta.total_seconds())
        return 0

    def is_dispute_critical(self):
        return self.remaining_dispute_seconds() <= 12 * 3600

    # Aliases for backward compatibility
    def remaining_seconds(self):
        return self.remaining_dispute_seconds()

    def is_critical(self):
        return self.is_dispute_critical()

    # ========== BOOKING HOLD METHODS ==========
    def get_hold_seconds_remaining(self):
        hold_end = self.created_at + timedelta(hours=72)
        now = timezone.now()
        if now >= hold_end:
            return 0
        return (hold_end - now).total_seconds()

    def is_hold_expired(self):
        return self.get_hold_seconds_remaining() == 0

    def get_extra_days(self):
        if not self.move_in_date:
            return 0
        created_date = self.created_at.date()
        total_days = (self.move_in_date - created_date).days
        return max(0, total_days - 3)

    def calculate_penalty(self, rent_amount):
        extra_days = self.get_extra_days()
        if extra_days <= 0:
            return 0
        penalty_per_day = (rent_amount * 0.5) / 100
        return extra_days * penalty_per_day

    def apply_penalty_if_due(self, rent_amount):
        if self.penalty_applied or self.status != 'paid':
            return 0
        penalty = self.calculate_penalty(rent_amount)
        if penalty > 0:
            self.penalty_amount = penalty
            self.penalty_applied = True
            self.amount -= penalty
            self.save()
        return penalty

    def auto_release(self, rent_amount):
        """
        Release the unit, apply penalty (if any), refund remaining to tenant,
        and mark as auto_released with a resolution note.
        """
        if self.auto_released or not self.is_hold_expired():
            return False

        # Apply penalty
        self.apply_penalty_if_due(rent_amount)

        # Release the unit
        if self.unit:
            self.unit.status = 'available'
            self.unit.save()

        # Set status and note
        self.status = 'auto_released'
        self.auto_released = True
        self.dispute_resolution_notes = (
            f"Auto-released after 72 hours without move-in. "
            f"Penalty applied: {'Yes' if self.penalty_applied else 'No'}. "
            f"Remaining amount: KES {self.amount:.2f}."
        )
        self.save()

        # (Optional) Send notifications here
        return True

    def __str__(self):
        return f"Escrow {self.id} - {self.unit} ({self.status})"
    
class DisputeMessage(models.Model):
    escrow = models.ForeignKey(EscrowTransaction, on_delete=models.CASCADE, related_name='dispute_messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_dispute_messages')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_dispute_messages')
    message = models.TextField()
    is_admin = models.BooleanField(default=False)  # so tenant knows it's from admin
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dispute {self.escrow.id}: {self.sender} -> {self.receiver}"
    
class DisputeEvidence(models.Model):
    escrow = models.ForeignKey(EscrowTransaction, on_delete=models.CASCADE, related_name='evidence')
    file = models.FileField(upload_to='dispute_evidence/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Evidence for Escrow {self.escrow.id}"