from django.contrib import admin
from django.urls import path
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import EscrowTransaction, DisputeMessage, DisputeEvidence   # ✅ added DisputeEvidence
from users.models import User
from properties.models import Notification
@admin.register(DisputeEvidence)

class DisputeEvidenceAdmin(admin.ModelAdmin):
    list_display = ('escrow', 'file', 'uploaded_at')

@admin.action(description='Release funds to landlord (resolve dispute in favor of landlord)')
def resolve_release(modeladmin, request, queryset):
    for escrow in queryset:
        if escrow.status == 'disputed':
            escrow.status = 'released'
            escrow.dispute_resolved = True
            escrow.save()
    messages.success(request, f"{queryset.count()} escrow(s) marked as released.")


@admin.action(description='Refund funds to tenant (resolve dispute in favor of tenant)')
def resolve_refund(modeladmin, request, queryset):
    for escrow in queryset:
        if escrow.status == 'disputed':
            escrow.status = 'refunded'
            escrow.dispute_resolved = True
            escrow.save()
    messages.success(request, f"{queryset.count()} escrow(s) refunded.")


@admin.action(description='Mark selected escrows as paid and start dispute window')
def mark_as_paid(modeladmin, request, queryset):
    count = 0
    for escrow in queryset:
        if escrow.status == 'pending':
            escrow.status = 'paid'
            escrow.start_dispute_window()
            escrow.save()
            count += 1
    messages.success(request, f"{count} escrow(s) marked as paid and dispute window started.")


class EscrowTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'property', 'tenant', 'landlord', 'amount', 'status', 'dispute_reason', 'created_at')
    list_filter = ('status', 'dispute_resolved')
    search_fields = ('tenant__username', 'landlord__username', 'property__title', 'dispute_reason')
    actions = [resolve_release, resolve_refund, mark_as_paid]
    readonly_fields = ('created_at', 'updated_at')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('disputes/', self.admin_site.admin_view(self.disputes_list), name='disputes_list'),
            path('dispute-chat/<int:escrow_id>/', self.admin_site.admin_view(self.dispute_chat), name='dispute_chat'),
            path('resolve-release/<int:escrow_id>/', self.admin_site.admin_view(self.resolve_dispute_release), name='resolve_dispute_release'),
            path('resolve-refund/<int:escrow_id>/', self.admin_site.admin_view(self.resolve_dispute_refund), name='resolve_dispute_refund'),
        ]
        return custom_urls + urls

    def disputes_list(self, request):
        disputed_escrows = EscrowTransaction.objects.filter(status='disputed').order_by('-created_at')
        context = {
            'title': 'Disputes',
            'disputed_escrows': disputed_escrows,
            'opts': self.model._meta,
        }
        return render(request, 'admin/payments/disputes_list.html', context)

    def dispute_chat(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, id=escrow_id, status='disputed')
        tenant = escrow.tenant

        if request.method == 'POST':
            message = request.POST.get('message')
            if message:
                DisputeMessage.objects.create(
                    escrow=escrow,
                    sender=request.user,
                    receiver=tenant,
                    message=message,
                    is_admin=True
                )
                Notification.objects.create(
                    user=tenant,
                    title="New message from support",
                    message=f"Support has responded to your dispute regarding {escrow.property.title}.",
                    link=f"/dispute-chat/{escrow.id}/"
                )
                messages.success(request, "Message sent to tenant.")
                return redirect('admin:dispute_chat', escrow_id=escrow.id)

        messages_history = DisputeMessage.objects.filter(escrow=escrow).order_by('created_at')

        # Evidence handling – using the correct model
        evidence = DisputeEvidence.objects.filter(escrow=escrow)  # ✅ direct query

        context = {
            'title': f'Dispute Chat – Property: {escrow.property.title}',
            'escrow': escrow,
            'messages': messages_history,
            'tenant': tenant,
            'evidence': evidence,
            'opts': self.model._meta,
        }
        return render(request, 'admin/payments/dispute_chat.html', context)

    def resolve_dispute_release(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
        if escrow.status == 'disputed':
            escrow.status = 'released'
            escrow.dispute_resolved = True
            escrow.save()

            Notification.objects.create(
                user=escrow.tenant,
                title="Dispute Resolved – Funds Released",
                message=f"The dispute for {escrow.property.title} has been resolved. The funds (KES {escrow.amount}) have been released to the landlord.",
                link=f"/escrow/status/{escrow.id}/"
            )
            Notification.objects.create(
                user=escrow.landlord,
                title="Dispute Resolved – Funds Released",
                message=f"The dispute for {escrow.property.title} has been resolved. Funds (KES {escrow.amount}) have been released to you.",
                link=f"/escrow/status/{escrow.id}/"
            )
            messages.success(request, "Funds released to landlord. Both parties have been notified.")
        return redirect('admin:disputes_list')

    def resolve_dispute_refund(self, request, escrow_id):
        escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
        if escrow.status == 'disputed':
            escrow.status = 'refunded'
            escrow.dispute_resolved = True
            escrow.save()

            Notification.objects.create(
                user=escrow.tenant,
                title="Dispute Resolved – Refund Issued",
                message=f"The dispute for {escrow.property.title} has been resolved. A refund of KES {escrow.amount} has been issued to you.",
                link=f"/escrow/status/{escrow.id}/"
            )
            Notification.objects.create(
                user=escrow.landlord,
                title="Dispute Resolved – Refund Issued",
                message=f"The dispute for {escrow.property.title} has been resolved. A refund of KES {escrow.amount} has been issued to the tenant.",
                link=f"/escrow/status/{escrow.id}/"
            )
            messages.success(request, "Funds refunded to tenant. Both parties have been notified.")
        return redirect('admin:disputes_list')


admin.site.register(EscrowTransaction, EscrowTransactionAdmin)