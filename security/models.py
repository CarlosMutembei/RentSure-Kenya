from django.db import models
from django.conf import settings
from properties.models import Property

class BlacklistEntry(models.Model):
    ENTRY_TYPES = (
        ('phone', 'Phone Number'),
        ('id_number', 'ID Number'),
        ('mpesa_account', 'M-Pesa Account'),
        ('device_fingerprint', 'Device Fingerprint'),
        ('email', 'Email Address'),
    )
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES)
    value = models.CharField(
        max_length=255,
        verbose_name="Identifier",
        help_text="Enter the phone number, ID number, email, or M-Pesa account (depending on the entry type)."
    )
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('entry_type', 'value')

    def __str__(self):
        return f"{self.get_entry_type_display()}: {self.value}"


class SuspiciousFlag(models.Model):
    FLAG_TYPES = (
        ('duplicate_listing', 'Duplicate Listing'),
        ('unrealistic_price', 'Unrealistic Price'),
        ('high_volume', 'High Posting Volume'),
        ('similar_description', 'Copied Description'),
        ('duplicate_image', 'Duplicate Image'),
        ('unusual_messaging', 'Unusual Messaging'),
        ('fake_payment', 'Fake Payment'),
    )
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='suspicious_flags')
    flag_type = models.CharField(max_length=30, choices=FLAG_TYPES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_flags')

    def __str__(self):
        return f"{self.get_flag_type_display()} on {self.property.title}"


class DeviceFingerprint(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='devices')
    fingerprint = models.CharField(max_length=255, unique=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.fingerprint[:20]}..."