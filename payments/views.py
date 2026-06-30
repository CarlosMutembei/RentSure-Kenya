import json
from decimal import Decimal
from datetime import timedelta
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse

from properties.models import Property, Unit, Notification
from .models import EscrowTransaction, Transaction, DisputeMessage, DisputeEvidence
import uuid

# ====================== LISTING FEE PAYMENT ======================
@login_required
def pay_listing_fee(request, property_id):
    """
    Handle payment of listing fee (KES 200) for newly created properties.
    Uses sandbox simulation for development.
    """
    property_obj = get_object_or_404(Property, id=property_id)

    # Permission check
    if request.user not in [property_obj.landlord, getattr(property_obj, 'agent', None)]:
        messages.error(request, "You are not authorized to pay for this property listing.")
        return redirect('dashboard')

    listing_fee_amount = 200  # KES 200

    if request.method == 'POST':
        # SANDBOX SIMULATION - Auto-approve in development
        property_obj.listing_fee_paid = True
        property_obj.is_verified = True
        property_obj.save()

        # Notify landlord
        Notification.objects.create(
            user=property_obj.landlord,
            title="🎉 Property Activated",
            message=f"Your property '{property_obj.title}' has been successfully listed and is now live.",
            link=reverse('property_detail', kwargs={'pk': property_obj.id}),
        )

        # Notify admins
        User = get_user_model()
        admins = User.objects.filter(is_superuser=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                title="🏢 New Property Listed",
                message=f"'{property_obj.title}' by {property_obj.landlord.username} is now live.",
                link=reverse('admin:properties_property_change', args=[property_obj.id]),
            )

        messages.success(
        request,  f"Payment simulated successfully! '{property_obj.title}' is now live.",
        extra_tags='payment_success')
        return redirect('property_detail', pk=property_obj.id)

    # GET request
    return render(request, 'payments/pay_listing_fee.html', {
        'property': property_obj,
        'fee': listing_fee_amount,
    })


# ====================== INITIATE ESCROW ======================
@login_required
def initiate_escrow(request, property_id, unit_id=None):
    """
    Initiate escrow payment for a property/unit.
    Supports both individual units and bulk unit types for any external user.
    """
    property_obj = get_object_or_404(Property, id=property_id)
    unit = None
    if unit_id:
        unit = get_object_or_404(Unit, id=unit_id, property=property_obj)

    # UPDATED: Permission checks allowing multi-role checkout, blocking only active listing managers
    is_owner = property_obj.landlord == request.user
    is_agent = hasattr(property_obj, 'agent') and property_obj.agent == request.user

    if is_owner or is_agent:
        messages.error(request, "You cannot book a property that you own or manage.")
        return redirect('property_detail', pk=property_id)

    # Calculate amounts
    monthly_rent = unit.monthly_rent if unit else property_obj.rent
    deposit_amount = unit.deposit if unit else (property_obj.deposit or Decimal('0'))

    escrow_amount = monthly_rent + deposit_amount
    platform_fee = min(monthly_rent * Decimal('0.03'), Decimal('500'))
    total_paid = escrow_amount + platform_fee

    today = timezone.now().date()
    default_move_in = today + timedelta(days=1)

    # Default penalty values
    penalty_per_day = monthly_rent * Decimal('0.02')  # 2% of rent per extra day
    max_penalty = Decimal('0')

    context = {
        'property': property_obj,
        'unit': unit,
        'monthly_rent': monthly_rent,
        'deposit_amount': deposit_amount,
        'escrow_amount': escrow_amount,
        'platform_fee': platform_fee,
        'total_paid': total_paid,
        'today': today,
        'move_in_date': default_move_in.isoformat(),
        'penalty_per_day': penalty_per_day,
        'max_penalty': max_penalty,
        'penalty_consent_needed': False,
    }

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        move_in_date_str = request.POST.get('move_in_date')

        if not phone or not move_in_date_str:
            messages.error(request, "Phone number and move-in date are required.")
            return render(request, 'payments/initiate_escrow.html', context)

        # Phone normalization
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone

        try:
            move_in_date = datetime.datetime.strptime(move_in_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return render(request, 'payments/initiate_escrow.html', context)

        if move_in_date < today:
            messages.error(request, "Move-in date cannot be in the past.")
            return render(request, 'payments/initiate_escrow.html', context)

        # Penalty calculation
        hold_days = (move_in_date - today).days
        extra_days = max(0, hold_days - 3)
        penalty_per_day = monthly_rent * Decimal('0.02')
        max_penalty = extra_days * penalty_per_day

        if extra_days > 0 and not request.POST.get('penalty_consent'):
            messages.warning(request, "Please accept the penalty terms to proceed.")
            context.update({
                'move_in_date': move_in_date_str,
                'penalty_per_day': penalty_per_day,
                'max_penalty': max_penalty,
                'penalty_consent_needed': True,
            })
            return render(request, 'payments/initiate_escrow.html', context)

        # ===================== SANDBOX SIMULATION =====================
        try:
            checkout_request_id = f"ws_CO_{uuid.uuid4().hex[:12]}"

            escrow = EscrowTransaction.objects.create(
                tenant=request.user,  # Stores the purchasing user instance
                landlord=property_obj.landlord,
                property=property_obj,
                unit=unit,
                amount=escrow_amount,
                platform_fee=platform_fee,
                move_in_date=move_in_date,
                status='pending',
                penalty_amount=max_penalty if extra_days > 0 else Decimal('0'),
                checkout_request_id=checkout_request_id,
            )

            messages.success(request, f"STK Push sent to {phone}. Please enter your M-Pesa PIN.")
            return redirect('escrow_status', escrow_id=escrow.id)

        except Exception as e:
            messages.error(request, f"Payment initiation failed: {str(e)}")
            return redirect('property_detail', pk=property_id)

    # GET request
    return render(request, 'payments/initiate_escrow.html', context)


# ====================== MPESA CALLBACK ======================
@csrf_exempt
def mpesa_callback(request):
    """
    Handle callback from M-Pesa (both listing fee and escrow payments).
    """
    try:
        data = json.loads(request.body)
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        checkout_request_id = stk_callback.get('CheckoutRequestID')

        mpesa_receipt = None
        if result_code == 0:
            items = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            for item in items:
                if item.get('Name') == 'MpesaReceiptNumber':
                    mpesa_receipt = item.get('Value')
                    break

        # === LISTING FEE PAYMENT ===
        property_obj = Property.objects.filter(checkout_request_id=checkout_request_id).first()
        if property_obj:
            if result_code == 0:
                property_obj.listing_fee_paid = True
                property_obj.is_verified = True
                property_obj.save()

                Notification.objects.create(
                    user=property_obj.landlord,
                    title="🎉 Property Activated",
                    message=f"Your property '{property_obj.title}' is now live.",
                    link=reverse('property_detail', kwargs={'pk': property_obj.id}),
                )
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

        # === ESCROW PAYMENT ===
        escrow = EscrowTransaction.objects.filter(checkout_request_id=checkout_request_id).first()
        if escrow:
            if result_code == 0:
                escrow.status = 'paid'
                escrow.mpesa_receipt = mpesa_receipt
                escrow.save()
                
                Notification.objects.create(
                    user=escrow.landlord,
                    title="💰 Escrow Payment Received",
                    message=f"Tenant paid KES {escrow.amount} for {escrow.property.title}.",
                    link=reverse('escrow_status', args=[escrow.id]),
                )
            else:
                escrow.status = 'failed'
                escrow.save()
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})

        return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback received"})

    except Exception as e:
        return JsonResponse({"ResultCode": 1, "ResultDesc": str(e)})


# ====================== ESCROW MANAGEMENT ======================
@login_required
def escrow_status(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    
    # Check permissions
    if request.user not in [escrow.tenant, escrow.landlord, escrow.unit.property.agent]:
        messages.error(request, "You don't have permission to view this transaction.")
        return redirect('dashboard')
    
    # Calculate refund amount if status is refunded or auto_released
    refund_amount = None
    refund_reason = None
    
    if escrow.status in ['refunded', 'auto_released']:
        refund_amount = escrow.amount  # The amount held after penalty
        refund_reason = escrow.dispute_resolution_notes or "Refund processed by admin"
        
        # If auto_released, also show the penalty deducted
        if escrow.status == 'auto_released' and escrow.penalty_applied:
            refund_reason = f"Auto-released (penalty of KES {escrow.penalty_amount:.2f} deducted). {refund_reason}"
    
    context = {
        'escrow': escrow,
        'refund_amount': refund_amount,
        'refund_reason': refund_reason,
    }
    return render(request, 'payments/escrow_status.html', context)


@login_required
def release_escrow(request, escrow_id):
    """Landlord releases escrow after move-in confirmation."""
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id, landlord=request.user)

    if escrow.status == 'paid':
        escrow.status = 'released'
        escrow.save()
        messages.success(request, "Escrow funds have been released to you.")
    else:
        messages.error(request, "Cannot release this escrow yet.")
    
    return redirect('dashboard')


@login_required
def confirm_move_in(request, escrow_id):
    """Tenant confirms they have moved in."""
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id, tenant=request.user)

    if escrow.status == 'paid':
        escrow.status = 'released'
        escrow.save()
        messages.success(request, "Move-in confirmed. Funds released to landlord.")
    else:
        messages.error(request, "Cannot confirm move-in at this time.")

    return redirect('dashboard')


# ====================== DISPUTE MANAGEMENT ======================
@login_required
def raise_dispute(request, escrow_id):
    """Tenant raises a dispute on escrow."""
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id, tenant=request.user)

    if request.method == 'POST':
        reason = request.POST.get('reason')
        if reason:
            escrow.status = 'disputed'
            escrow.dispute_reason = reason
            escrow.save()

            # Handle evidence files
            for f in request.FILES.getlist('evidence_files'):
                DisputeEvidence.objects.create(escrow=escrow, file=f)

            messages.success(request, "Dispute raised successfully. Our team will review it.")
            return redirect('dashboard')

    return render(request, 'payments/dispute_form.html', {'escrow': escrow})


@login_required
def tenant_dispute_chat(request, escrow_id):
    """Chat between tenant and support/landlord during dispute."""
    escrow = get_object_or_404(
        EscrowTransaction,
        id=escrow_id,
        tenant=request.user,
        status='disputed'
    )

    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            DisputeMessage.objects.create(
                escrow=escrow,
                sender=request.user,
                receiver=escrow.landlord,
                message=message,
            )
            messages.success(request, "Message sent.")
            return redirect('tenant_dispute_chat', escrow_id=escrow.id)

    # Mark messages as read
    DisputeMessage.objects.filter(
        escrow=escrow,
        receiver=request.user,
        is_read=False
    ).update(is_read=True)

    chat_messages = DisputeMessage.objects.filter(escrow=escrow).order_by('created_at')

    return render(request, 'payments/tenant_dispute_chat.html', {
        'escrow': escrow,
        'messages': chat_messages,
    })