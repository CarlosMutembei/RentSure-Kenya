from django.contrib import admin
from .models import BlacklistEntry, SuspiciousFlag, DeviceFingerprint


@admin.register(BlacklistEntry)
class BlacklistEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'entry_type', 'value', 'reason', 'created_by', 'created_at', 'is_active')
    list_filter = ('entry_type', 'is_active', 'created_at')
    search_fields = ('value', 'reason', 'created_by__username')
    list_editable = ('is_active',)                     # ✅ quick toggle active status
    readonly_fields = ('created_at',)
    actions = ['deactivate_entries', 'activate_entries']

    def save_model(self, request, obj, form, change):
        if not obj.pk:   # Only on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def deactivate_entries(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_entries.short_description = "Deactivate selected entries"

    def activate_entries(self, request, queryset):
        queryset.update(is_active=True)
    activate_entries.short_description = "Activate selected entries"


@admin.register(SuspiciousFlag)
class SuspiciousFlagAdmin(admin.ModelAdmin):
    list_display = ('id', 'property', 'flag_type', 'created_at', 'is_resolved')
    list_filter = ('flag_type', 'is_resolved', 'created_at')
    search_fields = ('property__title', 'description', 'property__town')
    list_editable = ('is_resolved',)                   # ✅ quick resolve toggle
    readonly_fields = ('created_at',)
    actions = ['mark_resolved', 'mark_unresolved']

    def mark_resolved(self, request, queryset):
        queryset.update(is_resolved=True)
    mark_resolved.short_description = "Mark selected as resolved"

    def mark_unresolved(self, request, queryset):
        queryset.update(is_resolved=False)
    mark_unresolved.short_description = "Mark selected as unresolved"


@admin.register(DeviceFingerprint)
class DeviceFingerprintAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'fingerprint_short', 'last_seen', 'created_at')
    list_filter = ('created_at', 'last_seen')
    search_fields = ('user__username', 'fingerprint', 'ip_address')
    readonly_fields = ('fingerprint', 'created_at', 'last_seen', 'ip_address', 'user_agent')
    fields = ('user', 'fingerprint', 'ip_address', 'user_agent', 'created_at', 'last_seen')

    def fingerprint_short(self, obj):
        return obj.fingerprint[:20] + '…' if obj.fingerprint else ''
    fingerprint_short.short_description = 'Fingerprint (truncated)'