from properties.models import Property   # add at top
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserRegistrationForm   # we'll create this next
from .models import Testimonial
from .models import AppLaunchLead
from .utils import geocode_address
from properties.models import ViewingAppointment
from payments.models import EscrowTransaction
from django.utils import timezone
from django.db import models
from django.db.models import Avg, Q, Sum, Count

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum, Q
from users.models import User
from properties.models import Property, PropertyReview
from payments.models import EscrowTransaction
from security.models import BlacklistEntry
from django.db.models import Case, When, Value, IntegerField

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            if 'profile_photo' in request.FILES:
                user.profile_photo = request.FILES['profile_photo']
            user.save()
            
            # ✅ Fix: Set the backend attribute before login
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            
            login(request, user)
            return redirect('home')
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # --- Blacklist check ---
            phone = getattr(user, 'phone', None)
            email = getattr(user, 'email', None)
            id_number = getattr(user, 'id_number', None)
            is_blacklisted = False

            if phone and BlacklistEntry.objects.filter(entry_type='phone', value=phone, is_active=True).exists():
                is_blacklisted = True
            elif email and BlacklistEntry.objects.filter(entry_type='email', value=email, is_active=True).exists():
                is_blacklisted = True
            elif id_number and BlacklistEntry.objects.filter(entry_type='id_number', value=id_number, is_active=True).exists():
                is_blacklisted = True

            if is_blacklisted:
                messages.error(request, "Your account has been blocked due to suspicious activity. Please contact support.")
                return render(request, 'registration/login.html')  # stay on login page with message
            else:
                login(request, user)
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'registration/login.html')

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
def profile_settings(request):
    if request.method == 'POST':
        # Update profile photo
        if request.FILES.get('profile_photo'):
            request.user.profile_photo = request.FILES['profile_photo']
            request.user.save()
            messages.success(request, 'Profile photo updated successfully!')
        # Update other fields if needed (e.g., phone, email)
        return redirect('profile_settings')
    return render(request, 'users/profile_settings.html', {'user': request.user})


@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}

    if user.role in ['landlord', 'agent']:
        properties_qs = Property.objects.filter(
            Q(landlord=user) | Q(agent=user),
            listing_fee_paid=True
        ).select_related('landlord').prefetch_related(
            'images', 'units'
        ).annotate(
            total_units_count=Count('units', distinct=True),
            available_units_count=Count('units', filter=Q(units__status='available'), distinct=True)
        ).order_by('-created_at')

        context['properties'] = properties_qs
        context['escrow_transactions'] = EscrowTransaction.objects.filter(
            Q(landlord=user) | Q(property__agent=user)
        ).order_by('-created_at')
        context['pending_viewings'] = ViewingAppointment.objects.filter(
            Q(property__landlord=user) | Q(property__agent=user),
            status='pending'
        ).count()

    elif user.role == 'tenant':
        context['saved_properties'] = user.saved_properties.select_related('property').all() \
            if hasattr(user, 'saved_properties') else []

        context['viewing_requests'] = ViewingAppointment.objects.filter(
            tenant=user
        ).order_by('-created_at')

        # ✅ Order escrows by priority: pending → paid → disputed → released → refunded → auto_released
        status_priority = Case(
            When(status='pending', then=Value(1)),
            When(status='paid', then=Value(2)),
            When(status='disputed', then=Value(3)),
            When(status='released', then=Value(4)),
            When(status='refunded', then=Value(5)),
            When(status='auto_released', then=Value(6)),
            default=Value(7),
            output_field=IntegerField(),
        )

        context['tenant_escrows'] = EscrowTransaction.objects.filter(
            tenant=user
        ).annotate(
            priority=status_priority
        ).order_by('priority', '-created_at')

    return render(request, 'users/dashboard.html', context)

@login_required
def submit_testimonial(request):
    if request.method == 'POST':
        content = request.POST.get('content')
        rating = request.POST.get('rating', 5)
        if content:
            Testimonial.objects.create(
                user=request.user,
                name=request.user.get_full_name() or request.user.username,
                content=content,
                rating=int(rating),
                is_approved=False
            )
            messages.success(request, "Thank you! Your testimonial will appear after review.")
        else:
            messages.error(request, "Please write something.")
        return redirect('home')
    return render(request, 'users/submit_testimonial.html')



def app_lead(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if email:
            lead, created = AppLaunchLead.objects.get_or_create(email=email)
            if created:
                messages.success(request, "Thanks! We'll notify you when the app launches.")
            else:
                messages.info(request, "You're already on the list.")
        else:
            messages.error(request, "Please enter a valid email.")
    return redirect('home')

@login_required
def update_location(request):
    if request.method == 'POST':
        town = request.POST.get('town')
        estate = request.POST.get('estate')
        lat = request.POST.get('latitude')
        lng = request.POST.get('longitude')
        
        if town and lat and lng:
            request.user.default_town = town
            request.user.default_estate = estate
            request.user.default_latitude = lat
            request.user.default_longitude = lng
            request.user.save()
            messages.success(request, "Your default location has been updated. Now use 'Near me' search!")
        else:
            messages.error(request, "Please select a location on the map and enter town/estate.")
        return redirect('dashboard')
    
    # For GET request, show the form with map
    return render(request, 'users/update_location.html', {'user': request.user})


@login_required
def set_default_location(request):
    if request.method == 'POST':
        place = request.POST.get('place')
        if place:
            geo = geocode_address(place)
            if geo:
                user = request.user
                user.default_latitude = geo['lat']
                user.default_longitude = geo['lng']
                user.default_town = geo['town']
                user.save()
                messages.success(request, f"Your default location is now {geo['town']}")
            else:
                messages.error(request, "Could not find that location. Please try again.")
        else:
            messages.error(request, "Please enter a location name.")
    return redirect('profile')   # or wherever your profile page is

@login_required
def kyc_submit(request):
    if request.user.role not in ['landlord', 'agent']:
        messages.error(request, "Only landlords and agents can submit KYC.")
        return redirect('dashboard')
    
    # Prevent resubmission if already pending or verified
    if request.user.kyc_status == 'pending':
        messages.warning(request, "Your KYC is already under review. Please wait for approval.")
        return redirect('dashboard')
    if request.user.kyc_status == 'verified':
        messages.info(request, "Your KYC is already verified.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        request.user.kyc_id_number = request.POST.get('id_number')
        request.user.kyc_kra_pin = request.POST.get('kra_pin')
        if request.FILES.get('document'):
            request.user.kyc_document = request.FILES['document']
        request.user.kyc_status = 'pending'
        request.user.kyc_submitted_at = timezone.now()
        request.user.save()
        messages.success(request, "KYC submitted. Admin will review.")
        return redirect('dashboard')
    return render(request, 'users/kyc_form.html')

@staff_member_required
def admin_dashboard(request):
    total_users = User.objects.count()
    landlords = User.objects.filter(role='landlord').count()
    tenants = User.objects.filter(role='tenant').count()
    agents = User.objects.filter(role='agent').count()
    pending_kyc = User.objects.filter(kyc_status='pending').count()

    total_properties = Property.objects.count()
    verified_properties = Property.objects.filter(is_verified=True).count()
    featured_properties = Property.objects.filter(is_featured=True).count()

    escrow_stats = EscrowTransaction.objects.aggregate(
        total=Sum('amount'),
        pending=Count('id', filter=models.Q(status='pending')),
        paid=Count('id', filter=models.Q(status='paid')),
        released=Count('id', filter=models.Q(status='released')),
        disputed=Count('id', filter=models.Q(status='disputed'))
    )
    total_escrow_amount = escrow_stats['total'] or 0
    pending_escrow = escrow_stats['pending']
    paid_escrow = escrow_stats['paid']
    released_escrow = escrow_stats['released']
    disputed_escrow = escrow_stats['disputed']

    avg_rating = PropertyReview.objects.aggregate(Avg('rating'))['rating__avg'] or 0

    recent_escrows = EscrowTransaction.objects.order_by('-created_at')[:10]

    context = {
        'total_users': total_users,
        'landlords': landlords,
        'tenants': tenants,
        'agents': agents,
        'pending_kyc': pending_kyc,
        'total_properties': total_properties,
        'verified_properties': verified_properties,
        'featured_properties': featured_properties,
        'total_escrow_amount': total_escrow_amount,
        'pending_escrow': pending_escrow,
        'paid_escrow': paid_escrow,
        'released_escrow': released_escrow,
        'disputed_escrow': disputed_escrow,
        'avg_rating': round(avg_rating, 1),
        'recent_escrows': recent_escrows,
    }
    return render(request, 'admin/analytics_dashboard.html', context)

@login_required
def verification_center(request):
    if request.user.role not in ['landlord', 'agent']:
        messages.error(request, "Only landlords and agents can access verification.")
        return redirect('dashboard')
    # Redirect to KYC submission if not verified or pending? Actually pending also needs to go to submission? No, pending should show waiting message.
    # You probably want to redirect only if not submitted or rejected.
    if request.user.kyc_status == 'verified':
        messages.info(request, "You are already verified.")
        return redirect('dashboard')
    elif request.user.kyc_status == 'pending':
        messages.info(request, "Your KYC is pending review.")
        return redirect('dashboard')
    else:
        return redirect('kyc_submit')