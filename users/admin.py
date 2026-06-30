from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from django.utils.html import format_html
from .models import User, Testimonial, AppLaunchLead

@admin.action(description='Approve KYC (Verified)')
def approve_kyc(modeladmin, request, queryset):
    for user in queryset:
        user.kyc_status = 'verified'
        user.kyc_verified_at = timezone.now()
        user.save()
    messages.success(request, f"{queryset.count()} user(s) KYC approved.")

@admin.action(description='Reject KYC')
def reject_kyc(modeladmin, request, queryset):
    for user in queryset:
        user.kyc_status = 'rejected'
        user.verification_status = 'rejected'
        user.is_verified = False
        user.save()
    messages.success(request, f"{queryset.count()} user(s) KYC rejected.")

class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'kyc_status', 'kyc_submitted_at', 'kyc_document_link')
    list_filter = ('role', 'kyc_status')
    search_fields = ('username', 'email', 'kyc_id_number')
    actions = [approve_kyc, reject_kyc]
    readonly_fields = ('kyc_submitted_at', 'kyc_verified_at')
    
    def kyc_document_link(self, obj):
        if obj.kyc_document:
            return format_html('<a href="{}" target="_blank">View Document</a>', obj.kyc_document.url)
        return '-'
    kyc_document_link.short_description = 'KYC Document'

class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('name', 'rating', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'rating')
    list_editable = ('is_approved',)

class AppLaunchLeadAdmin(admin.ModelAdmin):
    list_display = ('email', 'created_at')
    search_fields = ('email',)

admin.site.register(User, UserAdmin)
admin.site.register(Testimonial, TestimonialAdmin)
admin.site.register(AppLaunchLead, AppLaunchLeadAdmin)