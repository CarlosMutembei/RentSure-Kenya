import os
import uuid
from io import BytesIO

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models import PointField
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Max, Min, Q
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont


class Property(models.Model):
    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'landlord'},
        related_name='properties'
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'agent'},
        related_name='managed_properties'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    # Video walkthrough
    video = models.FileField(upload_to='property_videos/', blank=True, null=True)
    
    # Location
    location = PointField(srid=4326, geography=True, null=True, blank=True)
    address_text = models.CharField(max_length=300)
    town = models.CharField(max_length=100, blank=True)
    estate = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    formatted_address = models.TextField(blank=True)

    # Global amenities (shared across all units) – building‑wide
    wifi = models.BooleanField(default=False, help_text="Building has Wi-Fi")
    pets_allowed = models.BooleanField(default=False, help_text="Pets allowed in the building")
    
    # ========== NEW SHARED BUILDING AMENITIES ==========
    service_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        help_text="Monthly service charge for common areas"
    )
    has_water = models.BooleanField(default=True, help_text="Does the building have water supply?")
    has_electricity = models.BooleanField(default=True, help_text="Does the building have electricity?")
    has_parking = models.BooleanField(default=False, help_text="Does the building have parking?")
    has_security = models.BooleanField(default=False, help_text="Does the building have security?")
    # ===================================================

    # Verification & status
    is_verified = models.BooleanField(default=False)
    listing_fee_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)  # soft delete flag
    
    # Metrics & Rules
    views_count = models.PositiveIntegerField(default=0)
    rules = models.TextField(blank=True, null=True, help_text="House rules, pet policy, smoking, etc.")

    class Meta:
        indexes = [
            models.Index(fields=['town']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['is_verified', 'created_at']),
        ]
        verbose_name_plural = "Properties"

    def __str__(self):
        return f"{self.title} - {self.town}"

    def available_units_count(self):
        return self.units.filter(status='available').count()

    def total_units_count(self):
        return self.units.count()

    @property
    def price_range(self):
        """Returns a dict with the min and max monthly rent of associated units."""
        prices = self.units.aggregate(min_p=Min('monthly_rent'), max_p=Max('monthly_rent'))
        return {
            'min': prices['min_p'] or 0,
            'max': prices['max_p'] or 0
        }
        
    @property
    def starting_total_cost(self):
        """Returns the lowest rent price plus the base property service charge."""
        return self.price_range['min'] + float(self.service_charge)

    @property
    def scam_score(self):
        score = 0
        if self.is_verified:
            score -= 20

        if hasattr(self.landlord, 'kyc_status') and self.landlord.kyc_status == 'verified':
            score -= 30

        if self.agent and hasattr(self.agent, 'kyc_status') and self.agent.kyc_status == 'verified':
            score -= 20

        reference_date = self.created_at or timezone.now()
        days_old = (timezone.now() - reference_date).days
        if days_old > 30:
            score -= 10

        min_rent = self.price_range['min']
        if min_rent and min_rent < 10000:
            score += 30

        if score <= 10:
            return "Low Risk"
        elif score <= 40:
            return "Medium Risk"
        else:
            return "High Risk"


class Amenity(models.Model):
    """Property-wide amenities (e.g., swimming pool, gym, clubhouse)"""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='amenities')
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Amenities"
        constraints = [
            models.UniqueConstraint(fields=['property', 'name'], name='unique_amenity_per_property')
        ]

    def __str__(self):
        return self.name


class Unit(models.Model):
    UNIT_TYPES = (
        ('bedsitter', 'Bedsitter'),
        ('1br', '1 Bedroom'),
        ('2br', '2 Bedrooms'),
        ('3br', '3 Bedrooms'),
        ('studio', 'Studio'),
        ('single', 'Single Room'),
        ('double', 'Double Room (shared)'),
        ('short_single', 'Short-stay Single'),
        ('short_1br', 'Short-stay 1 Bedroom'),
        ('commercial', 'Commercial / Shop Front'),
        ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('booked', 'Booked (pending move-in)'),
        ('maintenance', 'Under Maintenance'),
    )
    PROPERTY_TYPE_CHOICES = (
        ('rental', 'Long‑term Rental'),
        ('bnb', 'Bed & Breakfast'),
        ('lodging', 'Lodging (daily)'),
        ('short_stay', 'Short‑stay (weekly)'),
    )

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='units')
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES)
    unit_number = models.CharField(max_length=20, blank=True, null=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    available_from = models.DateField(default=timezone.now)
    
    # ========== UNIT-SPECIFIC AMENITIES ==========
    furnished = models.BooleanField(default=False, help_text="Is this unit fully furnished?")
    has_water = models.BooleanField(default=True, help_text="Does this unit have water access?")
    has_electricity = models.BooleanField(default=True, help_text="Does this unit have electricity?")
    has_parking = models.BooleanField(default=False, help_text="Does this unit have parking?")
    has_security = models.BooleanField(default=False, help_text="Does this unit have dedicated security?")
    # ============================================

    occupied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='occupied_units'
    )
    booking_expires = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES, default='rental')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['property', 'unit_number'],
                name='unique_unit_number_per_property',
                condition=Q(unit_number__isnull=False)
            )
        ]

    def __str__(self):
        return f"{self.property.title} - {self.get_unit_type_display()} {self.unit_number or ''}"

    def clean(self):
        if self.unit_number and Unit.objects.filter(
            property=self.property,
            unit_number=self.unit_number
        ).exclude(pk=self.pk).exists():
            raise ValidationError("Unit number already exists for this property.")

    # ========== NEW METHOD ==========
    def get_bedrooms(self):
        """
        Return the number of bedrooms based on unit_type.
        Used in templates to display bedroom count.
        """
        mapping = {
            'bedsitter': 0,
            'studio': 0,
            'single': 0,
            'double': 1,          # shared double room typically has 1 bedroom
            '1br': 1,
            '2br': 2,
            '3br': 3,
            'short_single': 0,
            'short_1br': 1,
            'commercial': 0,
            'other': 0,
        }
        return mapping.get(self.unit_type, 0)


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='properties/')
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            img = Image.open(self.image)
            # Ensure proper handling of transparency/RGBA conversions
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")

            width, height = img.size
            
            # Create a transparent overlay for watermarking
            overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            
            font_size = int(min(width, height) * 0.04)
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()

            text = "RentSure Kenya"
            bbox = draw.textbbox((0, 0), text, font=font)
            textwidth = bbox[2] - bbox[0]
            textheight = bbox[3] - bbox[1]
            
            x = width - textwidth - 20
            y = height - textheight - 20
            
            # Draw semi-transparent white text onto overlay layer
            draw.text((x, y), text, fill=(255, 255, 255, 140), font=font)
            
            # Composite watermarked text seamlessly over the base picture
            watermarked_img = Image.alpha_composite(img.convert("RGBA"), overlay)
            final_img = watermarked_img.convert("RGB")

            output = BytesIO()
            final_img.save(output, format='JPEG', quality=85)
            output.seek(0)
            
            self.image.save(
                os.path.basename(self.image.name),
                ContentFile(output.read()),
                save=False
            )
            
        super().save(*args, **kwargs)


class PropertyReview(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='reviews')
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)], default=5)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.property.title} - {self.rating}★"


class SavedProperty(models.Model):
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_properties')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Saved Properties"
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'property'], name='unique_tenant_saved_property')
        ]

    def __str__(self):
        return f"{self.tenant.username} saved {self.property.title}"


class ViewingAppointment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    )
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='viewing_requests')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='viewings')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)  
    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    message = models.TextField(blank=True, help_text="Any extra info for the landlord")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    qr_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    reminder_sent = models.BooleanField(default=False)
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = uuid.uuid4().hex[:32]
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.tenant.username} - {self.property.title} ({self.status})"


class ChatMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='chats')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender} → {self.receiver}: {self.message[:20]}"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class FavoriteEstate(models.Model):
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_estates')
    estate = models.CharField(max_length=100)
    town = models.CharField(max_length=100)
    county = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'estate', 'town'], name='unique_tenant_estate_town')
        ]

    def __str__(self):
        return f"{self.tenant.username} - {self.estate}, {self.town}"


class ScamReport(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('investigating', 'Under Investigation'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    )
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scam_reports')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True, blank=True)
    landlord = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='reported_as_scam')
    description = models.TextField()
    evidence = models.FileField(upload_to='scam_evidence/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Report by {self.reported_by.username} on {self.property.title if self.property else 'landlord'}"