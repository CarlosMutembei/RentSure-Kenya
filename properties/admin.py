from django.contrib import admin
from .models import Property, PropertyImage, Amenity, Unit


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 1
    fields = (
        'unit_type', 'unit_number', 'monthly_rent', 'deposit',
        'status', 'available_from', 'property_type',
        'furnished', 'has_water', 'has_electricity', 'has_parking', 'has_security'
    )
    show_change_link = True


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'town', 'estate', 'get_rent_range',
        'is_verified', 'is_active', 'is_featured', 'created_at'
    )
    list_editable = ('is_verified', 'is_active')
    list_filter = ('is_verified', 'is_active', 'town', 'is_featured', 'county')
    search_fields = ('title', 'town', 'estate', 'county')
    inlines = [UnitInline]

    fieldsets = (
        (None, {
            'fields': ('landlord', 'agent', 'title', 'description', 'service_charge')
        }),
        ('Location', {
            'fields': ('town', 'estate', 'county', 'city', 'address_text', 'location', 'formatted_address')
        }),
        ('Building Amenities', {
            'fields': ('wifi', 'pets_allowed')
        }),
        ('Verification & Status', {
            'fields': ('is_verified', 'is_active', 'is_featured', 'listing_fee_paid', 'expires_at')
        }),
        ('Media', {
            'fields': ('video',)
        }),
    )

    @admin.display(description='Rent Range (KES)')
    def get_rent_range(self, obj):
        """Displays min and max rent from child units."""
        range_dict = obj.price_range
        if range_dict['min'] == 0 and range_dict['max'] == 0:
            return "No units"
        if range_dict['min'] == range_dict['max']:
            return f"{range_dict['min']:,}"
        return f"{range_dict['min']:,} – {range_dict['max']:,}"


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = (
        'unit_number', 'property', 'unit_type', 'monthly_rent',
        'status', 'furnished', 'property_type', 'available_from'
    )
    list_filter = ('status', 'unit_type', 'property_type', 'property__town', 'furnished')
    list_editable = ('status', 'monthly_rent', 'furnished')
    search_fields = ('unit_number', 'property__title', 'property__town')
    autocomplete_fields = ['property']

    fieldsets = (
        (None, {
            'fields': ('property', 'unit_type', 'unit_number', 'monthly_rent', 'deposit')
        }),
        ('Availability', {
            'fields': ('status', 'available_from', 'property_type')
        }),
        ('Unit Amenities', {
            'fields': ('furnished', 'has_water', 'has_electricity', 'has_parking', 'has_security')
        }),
    )


# Register remaining models
admin.site.register(PropertyImage)
admin.site.register(Amenity)