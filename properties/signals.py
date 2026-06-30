from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import Property, Unit
from security.models import SuspiciousFlag
from django.contrib.auth import get_user_model
from django.db.models import Avg, Min

User = get_user_model()

def check_suspicious(property):
    user = property.landlord

    # 1. High volume: more than 5 properties in last 24 hours
    recent_count = Property.objects.filter(
        landlord=user,
        created_at__gte=timezone.now() - timedelta(hours=24)
    ).count()
    if recent_count >= 5:
        SuspiciousFlag.objects.create(
            property=property,
            flag_type='high_volume',
            description=f"User posted {recent_count} properties in the last 24 hours."
        )

    # 2. Unrealistic price: check against average rent in the same town
    # Compute average monthly rent of all units belonging to verified properties in the same town
    avg_rent = Unit.objects.filter(
        property__town=property.town,
        property__is_verified=True
    ).aggregate(Avg('monthly_rent'))['monthly_rent__avg']

    # Get the minimum monthly rent among this property's units (if any exist)
    min_rent = property.units.aggregate(Min('monthly_rent'))['monthly_rent__min']

    if avg_rent and min_rent is not None and min_rent < avg_rent * 0.2:
        SuspiciousFlag.objects.create(
            property=property,
            flag_type='unrealistic_price',
            description=f"Minimum rent {min_rent} is less than 20% of average ({avg_rent}) in {property.town}."
        )

    # 3. Duplicate description
    duplicate = Property.objects.filter(
        description=property.description
    ).exclude(id=property.id).exists()
    if duplicate:
        SuspiciousFlag.objects.create(
            property=property,
            flag_type='similar_description',
            description="Property description matches an existing listing."
        )

@receiver(post_save, sender=Property)
def property_saved_handler(sender, instance, created, **kwargs):
    if created:
        # NOTE: At this point the property has just been saved but no units exist yet.
        # The price check will be skipped because min_rent will be None.
        # Consider moving this call to after unit creation in your view.
        check_suspicious(instance)