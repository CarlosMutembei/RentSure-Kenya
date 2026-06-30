from decimal import Decimal
from datetime import date, timedelta
import qrcode
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Prefetch, Avg, Min, Max, Count
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from users.models import Testimonial, User
from .forms import PropertyForm, ViewingAppointmentForm
from .models import (
    Property, Unit, PropertyReview, PropertyImage, SavedProperty,
    ChatMessage, ViewingAppointment, Notification, FavoriteEstate, ScamReport
)
from django.views.decorators.vary import vary_on_cookie 
from django.views.decorators.cache import cache_page

# ========================== HOME ==========================
from django.db.models import Avg, Min, Max, Subquery, OuterRef

def home(request):
    # ✅ Only include active properties (soft-deleted ones are hidden)
    base_qs = Property.objects.filter(is_active=True)

    # If tenant and have default location, prioritize nearby
    if (request.user.is_authenticated and request.user.role == 'tenant' and
            request.user.default_latitude and request.user.default_longitude):
        try:
            user_point = Point(
                float(request.user.default_longitude),
                float(request.user.default_latitude),
                srid=4326
            )
            nearby_qs = base_qs.filter(location__distance_lte=(user_point, D(km=20)))
            if nearby_qs.exists():
                base_qs = nearby_qs.annotate(
                    distance=Distance('location', user_point)
                ).order_by('-is_verified', 'distance')
            else:
                base_qs = base_qs.order_by('-is_verified', '-created_at')
        except (TypeError, ValueError):
            base_qs = base_qs.order_by('-is_verified', '-created_at')
    else:
        base_qs = base_qs.order_by('-is_verified', '-created_at')

    # Cached stats (only for active + verified properties)
    stats = cache.get('home_stats')
    if not stats:
        # ✅ Only active verified properties
        active_verified = Property.objects.filter(is_active=True, is_verified=True)
        avg_rent_val = active_verified.aggregate(
            avg_price=Avg('units__monthly_rent')
        )['avg_price'] or 0

        stats = {
            'verified_count': active_verified.count(),
            'town_count': active_verified.values('town').distinct().count(),
            'avg_rent': int(avg_rent_val),
        }
        cache.set('home_stats', stats, 60 * 15)

    # Map data: only active properties with a location
    map_properties_qs = base_qs.filter(
        location__isnull=False,
        is_active=True
    ).annotate(
        min_price=Min('units__monthly_rent'),
        max_price=Max('units__monthly_rent')
    )[:50]

    map_properties_list = []
    for prop in map_properties_qs:
        map_properties_list.append({
            'id': prop.id,
            'title': prop.title,
            'town': prop.town,
            'location': prop.location,
            'price_range': {
                'min': prop.min_price or 0,
                'max': prop.max_price or 0
            }
        })

    context = {
        'featured': base_qs.filter(is_featured=True, is_active=True)[:6],
        'verified': base_qs.filter(is_verified=True, is_active=True)[:8],
        'recent': base_qs.filter(is_active=True)[:6],
        'map_properties': map_properties_list,
        'testimonials': Testimonial.objects.filter(is_approved=True).order_by('-created_at')[:3],
        'stats': stats,
        'map_center': [-1.286389, 36.817223],
        'map_zoom': 12,
    }
    return render(request, 'properties/home.html', context)


# ========================== CREATE PROPERTY ==========================
@login_required
def create_property(request):
    if request.user.role not in ['landlord', 'agent']:
        messages.error(request, 'Only landlords and agents can post properties.')
        return redirect('dashboard')

    landlords_list = User.objects.filter(role='landlord') if request.user.role == 'agent' else None

    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            try:
                with transaction.atomic():
                    property_obj = form.save(commit=False)

                    # Owner/Agent assignment
                    if request.user.role == 'landlord':
                        property_obj.landlord = request.user
                        if form.cleaned_data.get('agent'):
                            property_obj.agent = form.cleaned_data['agent']
                    else:
                        landlord_id = request.POST.get('landlord_id')
                        if not landlord_id:
                            messages.error(request, "Please select the property owner.")
                            return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})

                        owner = get_object_or_404(User, id=landlord_id, role='landlord')
                        property_obj.landlord = owner
                        property_obj.agent = request.user

                    # Map coordinates
                    try:
                        lng = float(request.POST.get('lng'))
                        lat = float(request.POST.get('lat'))
                        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                            raise ValueError
                        property_obj.location = Point(lng, lat, srid=4326)
                    except (TypeError, ValueError):
                        messages.error(request, "Please select a valid location on the map.")
                        return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})

                    property_obj.expires_at = timezone.now() + timedelta(days=30)
                    property_obj.save()

                    # ==========================================================
                    # UNIT CREATION: BULK vs INDIVIDUAL
                    # ==========================================================
                    unit_mode = request.POST.get('unit_mode', 'bulk')

                    # Prefix mapping for unit numbers
                    UNIT_PREFIX_MAP = {
                        'studio': 'STU',
                        'bedsitter': 'BED',
                        'single': 'SIN',
                        'double': 'DBL',
                        '1br': '1BR',
                        '2br': '2BR',
                        '3br': '3BR',
                        'short-single': 'SHS',
                        'short-1br': 'SH1',
                        'commercial': 'COM',
                        'other': 'OTH',
                    }

                    if unit_mode == 'individual':
                        # --- Individual mode (unchanged) ---
                        cat = request.POST.get('unit_type', '').strip()
                        unit_num = request.POST.get('unit_number', '').strip()
                        rent_raw = request.POST.get('monthly_rent', '').strip()
                        rent = float(rent_raw) if rent_raw.replace('.', '', 1).isdigit() else 0.0
                        dep_raw = request.POST.get('deposit', '').strip()
                        deposit = float(dep_raw) if dep_raw.replace('.', '', 1).isdigit() else 0.0
                        status = request.POST.get('status', 'available')
                        is_furnished = request.POST.get('furnished') == 'on'
                        has_w = request.POST.get('has_water') == 'on'
                        has_e = request.POST.get('has_electricity') == 'on'
                        has_p = request.POST.get('has_parking') == 'on'
                        has_s = request.POST.get('has_security') == 'on'
                        avail_date_str = request.POST.get('available_from')
                        if avail_date_str:
                            try:
                                avail_date = timezone.datetime.strptime(avail_date_str, '%Y-%m-%d').date()
                            except ValueError:
                                avail_date = timezone.now().date()
                        else:
                            avail_date = timezone.now().date()

                        if cat and unit_num:
                            Unit.objects.create(
                                property=property_obj,
                                unit_type=cat,
                                unit_number=unit_num,
                                monthly_rent=rent,
                                deposit=deposit,
                                status=status,
                                available_from=avail_date,
                                furnished=is_furnished,
                                has_water=has_w,
                                has_electricity=has_e,
                                has_parking=has_p,
                                has_security=has_s,
                            )

                    else:
                        # --- BULK MODE ---
                        category_names = request.POST.getlist('unit_type[]')
                        totals = request.POST.getlist('unit_total[]')
                        rents = request.POST.getlist('unit_rent[]')
                        occupied = request.POST.getlist('unit_occupied[]')
                        booked = request.POST.getlist('unit_booked[]')
                        maintenance = request.POST.getlist('unit_repair[]')
                        furnished = request.POST.getlist('unit_furnished[]')
                        has_water = request.POST.getlist('has_water[]')
                        has_electricity = request.POST.getlist('has_electricity[]')
                        has_parking = request.POST.getlist('has_parking[]')
                        has_security = request.POST.getlist('has_security[]')

                        # Quick length check – all lists must match
                        if not (len(category_names) == len(totals) == len(rents) == len(occupied) == len(booked) == len(maintenance)):
                            messages.error(request, "Bulk unit data is incomplete or mismatched.")
                            return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})

                        for i in range(len(category_names)):
                            cat = category_names[i].strip()
                            total = int(totals[i]) if totals[i].strip().isdigit() else 0
                            if total <= 0:
                                continue

                            rent = float(rents[i]) if rents[i].strip().replace('.', '', 1).isdigit() else 0.0
                            occ = int(occupied[i]) if occupied[i].strip().isdigit() else 0
                            bk = int(booked[i]) if booked[i].strip().isdigit() else 0
                            maint = int(maintenance[i]) if maintenance[i].strip().isdigit() else 0

                            # 🔴 VALIDATION: occupied + booked + maintenance must be ≤ total
                            if occ + bk + maint > total:
                                messages.error(
                                    request,
                                    f"Group '{cat}': Occupied ({occ}) + Booked ({bk}) + Maintenance ({maint}) "
                                    f"exceeds total ({total}). Please adjust your numbers."
                                )
                                return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})

                            # Amenities for this category
                            is_furnished = i < len(furnished) and furnished[i] == 'on'
                            has_w = i < len(has_water) and has_water[i] == 'on'
                            has_e = i < len(has_electricity) and has_electricity[i] == 'on'
                            has_p = i < len(has_parking) and has_parking[i] == 'on'
                            has_s = i < len(has_security) and has_security[i] == 'on'

                            # Build statuses: occupied → booked → maintenance → available
                            statuses = ['occupied'] * occ + ['booked'] * bk + ['maintenance'] * maint
                            remaining = total - len(statuses)
                            if remaining > 0:
                                statuses += ['available'] * remaining
                            # In case of any discrepancy, trim to total
                            statuses = statuses[:total]

                            # Prefix for unit numbers
                            prefix = UNIT_PREFIX_MAP.get(cat, cat[:3].upper())
                            for j in range(total):
                                Unit.objects.create(
                                    property=property_obj,
                                    unit_type=cat,
                                    unit_number=f"{prefix}-{j + 101:03d}",
                                    monthly_rent=rent,
                                    deposit=0,  # deposit can be set later
                                    status=statuses[j] if j < len(statuses) else 'available',
                                    available_from=timezone.now().date(),
                                    furnished=is_furnished,
                                    has_water=has_w,
                                    has_electricity=has_e,
                                    has_parking=has_p,
                                    has_security=has_s,
                                )

                    # Save images and video
                    for i, image in enumerate(request.FILES.getlist('images')):
                        PropertyImage.objects.create(
                            property=property_obj,
                            image=image,
                            is_primary=(i == 0)
                        )
                    if video := request.FILES.get('video'):
                        property_obj.video = video
                        property_obj.save()

                    messages.success(request, "Property created successfully!")
                    return redirect('pay_listing_fee', property_id=property_obj.id)

            except Exception as e:
                messages.error(request, f"Error saving property: {e}")
                return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})

        else:
            for field, errors in form.errors.items():
                for error in errors:
                    field_name = field.replace('_', ' ').title() if field != '__all__' else "Form Error"
                    messages.error(request, f"❌ {field_name}: {error}")
            return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})

    else:
        form = PropertyForm(user=request.user)
        return render(request, 'properties/create.html', {'form': form, 'landlords': landlords_list})



# ========================== SEARCH ==========================
from datetime import date
def search(request):
    available_units_prefetch = Prefetch(
        'units',
        queryset=Unit.objects.filter(status='available', available_from__lte=date.today()),
        to_attr='available_units_list'
    )

    # UPDATED: Added is_active=True to the initial filter chain
    properties = Property.objects.filter(
        is_verified=True, 
        is_active=True
    ).select_related('landlord').prefetch_related(
        'images', available_units_prefetch
    )

    # Location filters
    if town := request.GET.get('town'):
        properties = properties.filter(
            Q(town__icontains=town) | Q(estate__icontains=town)
        )
    if county := request.GET.get('county'):
        properties = properties.filter(county__icontains=county)

    # Rent - FIX 1 & 2: Span across relationship to units__monthly_rent
    # Filter on matching available units specifically so price matching stays accurate
    try:
        if min_rent := request.GET.get('min_rent'):
            properties = properties.filter(
                units__monthly_rent__gte=float(min_rent),
                units__status='available',
                units__available_from__lte=date.today()
            )
        if max_rent := request.GET.get('max_rent'):
            properties = properties.filter(
                units__monthly_rent__lte=float(max_rent),
                units__status='available',
                units__available_from__lte=date.today()
            )
    except (ValueError, TypeError):
        pass

    # Bedrooms
    if bedrooms := request.GET.get('bedrooms'):
        if bedrooms != 'any':
            try:
                properties = properties.filter(bedrooms=int(bedrooms))
            except ValueError:
                pass

    # Amenities
    filters = {
        'furnished': 'furnished',
        'water': 'has_water',
        'parking': 'has_parking',
        'security': 'has_security',
        'wifi': 'wifi',
        'pets': 'pets_allowed',
    }
    for param, field in filters.items():
        if request.GET.get(param):
            properties = properties.filter(**{field: True})

    # Property type (on units)
    if property_type := request.GET.get('property_type'):
        if property_type != 'any':
            properties = properties.filter(units__property_type=property_type)

    # Near me
    is_ordered_by_distance = False
    lat = request.GET.get('lat') or (getattr(request.user, 'default_latitude', None) if request.user.is_authenticated else None)
    lng = request.GET.get('lng') or (getattr(request.user, 'default_longitude', None) if request.user.is_authenticated else None)

    if request.GET.get('near_me') and lat and lng:
        try:
            user_point = Point(float(lng), float(lat), srid=4326)
            radius = int(request.GET.get('radius', 20))
            properties = properties.filter(
                location__distance_lte=(user_point, D(km=radius))
            ).annotate(distance=Distance('location', user_point))
            is_ordered_by_distance = True
        except Exception:
            pass

    # Must have available units
    properties = properties.filter(
        units__status='available',
        units__available_from__lte=date.today()
    ).distinct() # Keeps base properties unique

    # Ordering - FIX 3: Changed fallback order from 'rent' to '-created_at' (newest listings first)
    properties = properties.order_by('distance' if is_ordered_by_distance else '-created_at')

    # Pagination
    paginator = Paginator(properties, 24)
    properties_page = paginator.get_page(request.GET.get('page'))

    context = {
        'properties': properties_page,
        'filters': request.GET.dict(),  # easier for template
        'distance_info': {},  
    }
    return render(request, 'properties/search_results.html', context)

# ========================== PROPERTY LIST (ALL PROPERTIES) ==========================
def property_list(request):
    """
    List all active, verified properties with unit-based filtering.
    Supports search by town, rent range, bedroom count, and amenities.
    """
    # Base queryset: only active and verified properties
    properties = Property.objects.filter(
        is_active=True,
        is_verified=True
    ).select_related('landlord').prefetch_related('images', 'units')

    # ---------- FILTERS ----------
    # 1. Location (town / estate)
    if town := request.GET.get('town'):
        properties = properties.filter(
            Q(town__icontains=town) | Q(estate__icontains=town)
        )

    # 2. Rent range (on units)
    try:
        if min_rent := request.GET.get('min_rent'):
            properties = properties.filter(units__monthly_rent__gte=float(min_rent))
        if max_rent := request.GET.get('max_rent'):
            properties = properties.filter(units__monthly_rent__lte=float(max_rent))
    except (ValueError, TypeError):
        pass

    # 3. Bedrooms (map to unit_type)
    bedrooms_map = {
        '0': ['studio', 'bedsitter', 'single', 'short_single'],
        '1': ['1br', 'double', 'short_1br'],
        '2': ['2br'],
        '3': ['3br'],
    }
    if bedrooms := request.GET.get('bedrooms'):
        if bedrooms != 'any' and bedrooms in bedrooms_map:
            properties = properties.filter(units__unit_type__in=bedrooms_map[bedrooms])

    # 4. Unit-level amenities
    amenity_map = {
        'furnished': 'furnished',
        'water': 'has_water',
        'parking': 'has_parking',
        'security': 'has_security',
        'wifi': 'wifi',  # building-wide; handled separately
    }
    for param, field in amenity_map.items():
        if request.GET.get(param):
            # Building-wide wifi is on Property, not Unit
            if field == 'wifi' and hasattr(Property, 'wifi'):
                properties = properties.filter(wifi=True)
            else:
                properties = properties.filter(**{f'units__{field}': True})

    # 5. Ensure at least one unit is available (optional)
    # If you only want properties with available units, uncomment:
    # properties = properties.filter(units__status='available')

    # Deduplicate and order
    properties = properties.distinct().order_by('-created_at')

    # ---------- PAGINATION ----------
    paginator = Paginator(properties, 12)  # 12 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ---------- STATISTICS (optional) ----------
    stats = {
        'verified_count': properties.count(),
        'town_count': properties.values('town').distinct().count(),
        'avg_rent': int(properties.aggregate(Avg('units__monthly_rent'))['units__monthly_rent__avg'] or 0),
    }

    context = {
        'properties': page_obj,
        'stats': stats,
        'filters': request.GET.dict(),
    }
    return render(request, 'properties/list.html', context)

# ========================== PROPERTY DETAIL ==========================
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.db.models import Avg, Min, Max, Count
from .models import Property, Unit, SavedProperty

def property_detail(request, pk):
    property_obj = get_object_or_404(Property, id=pk)
    print(f"🔍 property_detail called with pk={pk}")

    # Only show active properties (unless owner/agent is viewing)
    if not property_obj.is_active and request.user != property_obj.landlord and request.user != property_obj.agent:
        raise Http404("This property is no longer available.")

    # Available units
    available_units = property_obj.units.filter(status='available')

    # Price range
    price_range = property_obj.units.aggregate(
        min_rent=Min('monthly_rent'),
        max_rent=Max('monthly_rent')
    )
    price_range = {
        'min': price_range['min_rent'] or 0,
        'max': price_range['max_rent'] or 0,
    }

    # Reviews
    reviews = property_obj.reviews.filter(is_approved=True)
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0

    # Scam score
    scam_score = property_obj.scam_score

    # ---- Owner / Agent check ----
    is_owner = False
    is_agent = False
    if request.user.is_authenticated:
        is_owner = property_obj.landlord == request.user
        is_agent = property_obj.agent == request.user

    # ---- Saved Property ----
    is_saved = False
    if request.user.is_authenticated and not is_owner and not is_agent:
        is_saved = SavedProperty.objects.filter(
            tenant=request.user,
            property=property_obj
        ).exists()
    # (If the user is owner/agent, we still keep is_saved False to avoid save button confusion,
    # but the template will check is_owner/is_agent first.)

    # ----- Compare list handling (unit IDs) -----
    compare_unit_ids = []
    in_compare = False
    if request.user.is_authenticated and 'compare_list' in request.session:
        compare_unit_ids = request.session['compare_list']
        # check if any unit of this property is in compare list (optional)
        # but we keep the property-level in_compare as before
        if property_obj.id in compare_unit_ids:  # likely incorrect, but kept for compatibility
            in_compare = True

    # ----- Available unit types breakdown -----
    unit_type_breakdown = property_obj.units.filter(
        status='available'
    ).values('unit_type').annotate(count=Count('id'))

    type_display = []
    for item in unit_type_breakdown:
        type_name = dict(Unit.UNIT_TYPES).get(item['unit_type'], item['unit_type'])
        type_display.append(f"{type_name} ({item['count']})")
    unit_types_summary = ', '.join(type_display) if type_display else "None available"

    unit_types_count = property_obj.units.values('unit_type').distinct().count()

    context = {
        'property': property_obj,
        'available_units': available_units,
        'price_range': price_range,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'scam_score': scam_score,
        'is_saved': is_saved,
        'in_compare': in_compare,
        'compare_unit_ids': compare_unit_ids,
        'unit_types_count': unit_types_count,
        'unit_types_summary': unit_types_summary,
        'is_owner': is_owner,      # ✅ New
        'is_agent': is_agent,      # ✅ New
    }
    return render(request, 'properties/detail.html', context)


# ========================== UNIT MANAGEMENT ==========================
@login_required
def manage_units(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "Permission denied.")
        return redirect('property_detail', property_id=property_obj.id)

    # =====================================================
    # BULK ADD (from category arrays)
    # =====================================================
    if request.method == 'POST' and 'unit_type[]' in request.POST:
        category_names = request.POST.getlist('unit_type[]')
        totals = request.POST.getlist('unit_total[]')
        rents = request.POST.getlist('unit_rent[]')
        occupied = request.POST.getlist('unit_occupied[]')
        booked = request.POST.getlist('unit_booked[]')
        maintenance = request.POST.getlist('unit_repair[]')
        furnished = request.POST.getlist('unit_furnished[]')
        has_water = request.POST.getlist('has_water[]')
        has_electricity = request.POST.getlist('has_electricity[]')
        has_parking = request.POST.getlist('has_parking[]')
        has_security = request.POST.getlist('has_security[]')

        created_count = 0
        for i in range(len(category_names)):
            cat = category_names[i].strip()
            total = int(totals[i])
            rent = float(rents[i]) if rents[i] else 0
            occ = int(occupied[i]) if i < len(occupied) and occupied[i] else 0
            bk = int(booked[i]) if i < len(booked) and booked[i] else 0
            maint = int(maintenance[i]) if i < len(maintenance) and maintenance[i] else 0

            is_furnished = i < len(furnished) and furnished[i] == 'on'
            has_w = i < len(has_water) and has_water[i] == 'on'
            has_e = i < len(has_electricity) and has_electricity[i] == 'on'
            has_p = i < len(has_parking) and has_parking[i] == 'on'
            has_s = i < len(has_security) and has_security[i] == 'on'

            statuses = ['occupied'] * occ + ['booked'] * bk + ['maintenance'] * maint
            remaining = total - len(statuses)
            statuses += ['available'] * remaining

            # Find next available unit number suffix for this category
            existing = property_obj.units.filter(unit_type=cat).count()
            for j in range(total):
                prefix = cat[:3].upper()
                unit_number = f"{prefix}-{existing + j + 1:02d}"
                Unit.objects.create(
                    property=property_obj,
                    unit_type=cat,
                    unit_number=unit_number,
                    monthly_rent=rent,
                    deposit=0,
                    status=statuses[j],
                    available_from=timezone.now().date(),
                    furnished=is_furnished,
                    has_water=has_w,
                    has_electricity=has_e,
                    has_parking=has_p,
                    has_security=has_s,
                )
                created_count += 1

        messages.success(request, f"{created_count} unit(s) added in bulk!")
        return redirect('manage_units', property_id=property_obj.id)

    # =====================================================
    # INDIVIDUAL ADD (existing code)
    # =====================================================
    if request.method == 'POST':  # individual unit
        unit_number = request.POST.get('unit_number')
        if Unit.objects.filter(property=property_obj, unit_number=unit_number).exists():
            messages.error(request, f"Unit '{unit_number}' already exists.")
            return redirect('manage_units', property_id=property_obj.id)

        Unit.objects.create(
            property=property_obj,
            unit_type=request.POST.get('unit_type'),
            unit_number=unit_number,
            monthly_rent=request.POST.get('monthly_rent'),
            deposit=request.POST.get('deposit') or None,
            status=request.POST.get('status'),
            available_from=request.POST.get('available_from'),
            furnished=request.POST.get('furnished') == 'on',
            has_water=request.POST.get('has_water') == 'on',
            has_electricity=request.POST.get('has_electricity') == 'on',
            has_parking=request.POST.get('has_parking') == 'on',
            has_security=request.POST.get('has_security') == 'on',
        )
        messages.success(request, f"Unit '{unit_number}' added successfully!")
        return redirect('manage_units', property_id=property_obj.id)

    # GET – display page
    units = property_obj.units.all().order_by('unit_number')
    return render(request, 'properties/manage_units.html', {
        'property': property_obj,
        'units': units,
        'today': timezone.now().date().isoformat(),
    })

@login_required
def add_unit(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)
    
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "You don't have permission to add units.")
        return redirect('property_detail', property_id=property_obj.id)

    if request.method == 'POST':
        unit_number = request.POST.get('unit_number')
        
        if Unit.objects.filter(property=property_obj, unit_number=unit_number).exists():
            messages.error(request, f"Unit '{unit_number}' already exists.")
            return render(request, 'properties/add_unit.html', {
                'property': property_obj,
                'today': timezone.now().date().isoformat(),
            })

        Unit.objects.create(
            property=property_obj,
            unit_type=request.POST.get('unit_type'),
            unit_number=unit_number,
            monthly_rent=request.POST.get('monthly_rent'),
            deposit=request.POST.get('deposit') or None,
            status=request.POST.get('status'),
            available_from=request.POST.get('available_from'),
            furnished=request.POST.get('furnished') == 'on',
            has_water=request.POST.get('has_water') == 'on',
            has_electricity=request.POST.get('has_electricity') == 'on',
            has_parking=request.POST.get('has_parking') == 'on',
            has_security=request.POST.get('has_security') == 'on',
        )
        messages.success(request, f"Unit '{unit_number}' added successfully!")
        return redirect('manage_units', property_id=property_obj.id)

    return render(request, 'properties/add_unit.html', {
        'property': property_obj,
        'today': timezone.now().date().isoformat(),
    })
    
@login_required
def edit_property(request, pk):
    property_obj = get_object_or_404(Property, id=pk)
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "You don't have permission to edit this property.")
        return redirect('property_detail', pk=property_obj.id)

    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES, instance=property_obj, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Property updated successfully!")
            return redirect('property_detail', pk=property_obj.id)
    else:
        form = PropertyForm(instance=property_obj, user=request.user)

    return render(request, 'properties/edit_property.html', {
        'form': form,
        'property': property_obj,
    })
    
# Safe import for EscrowTransaction
try:
    from payments.models import EscrowTransaction
except ImportError:
    EscrowTransaction = None
    
@login_required
def delete_property(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)

    # Permissions
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "You don't have permission to delete this property.")
        return redirect('property_detail', property_id=property_obj.id)

    # Security checks
    has_active_issues = False
    error_messages = []

    # 1. Check for occupied or booked units
    occupied_units = property_obj.units.filter(status__in=['occupied', 'booked'])
    if occupied_units.exists():
        has_active_issues = True
        error_messages.append(f"{occupied_units.count()} unit(s) are currently occupied or booked. They must be vacated first.")

    # 2. Check for active escrow transactions (if the model exists)
    if EscrowTransaction is not None:
        active_escrows = EscrowTransaction.objects.filter(
            unit__property=property_obj,
            status__in=['pending', 'confirmed', 'disputed']
        )
        if active_escrows.exists():
            has_active_issues = True
            error_messages.append(f"{active_escrows.count()} active escrow transaction(s) exist. Resolve them first.")
    else:
        # Payments app not installed – skip this check
        pass

    if request.method == 'POST':
        if has_active_issues:
            messages.error(request, "Cannot delete property: " + " ".join(error_messages))
            return redirect('property_detail', property_id=property_obj.id)

        # Soft delete – mark as inactive
        property_obj.is_active = False
        property_obj.save()
        messages.success(request, f"Property '{property_obj.title}' has been deactivated and hidden from search.")
        return redirect('dashboard')

    # GET: show confirmation page
    return render(request, 'properties/delete_property.html', {
        'property': property_obj,
        'has_active_issues': has_active_issues,
        'error_messages': error_messages,
    })

@login_required
def edit_unit(request, property_id, unit_id):
    # ✅ First, get the property object
    property_obj = get_object_or_404(Property, id=property_id)
    
    # ✅ Then, get the unit object using both ID and property
    unit = get_object_or_404(Unit, id=unit_id, property=property_obj)

    # ✅ Check permission using the property_obj
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "You don't have permission to edit this unit.")
        return redirect('property_detail', property_id=property_obj.id)

    if request.method == 'POST':
        # ✅ Correctly assign to unit.attribute (not unit_attribute)
        unit.unit_type = request.POST.get('unit_type')
        unit.unit_number = request.POST.get('unit_number')
        unit.monthly_rent = request.POST.get('monthly_rent')
        unit.deposit = request.POST.get('deposit') or None
        unit.status = request.POST.get('status')
        unit.available_from = request.POST.get('available_from')
        
        # ✅ Boolean fields from checkboxes
        unit.furnished = request.POST.get('furnished') == 'on'
        unit.has_water = request.POST.get('has_water') == 'on'
        unit.has_electricity = request.POST.get('has_electricity') == 'on'
        unit.has_parking = request.POST.get('has_parking') == 'on'
        unit.has_security = request.POST.get('has_security') == 'on'
        
        # ✅ Save the unit
        unit.save()
        
        messages.success(request, f"Unit '{unit.unit_number}' updated successfully!")
        return redirect('manage_units', property_id=property_obj.id)

    return render(request, 'properties/edit_unit.html', {
        'property': property_obj,
        'unit': unit,
    })

@login_required
def delete_unit(request, property_id, unit_id):
    property_obj = get_object_or_404(Property, id=property_id)
    unit = get_object_or_404(Unit, id=unit_id, property=property_obj)
    
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "You don't have permission to delete this unit.")
        return redirect('property_detail', property_id=property_obj.id)

    if request.method == 'POST':
        unit_number = unit.unit_number
        unit.delete()
        messages.success(request, f"Unit '{unit_number}' deleted successfully!")
        return redirect('manage_units', property_id=property_obj.id)

    return render(request, 'properties/delete_unit.html', {
        'property': property_obj,
        'unit': unit,
    })


# ========================== IMAGES ==========================
@login_required
def manage_property_images(request, property_id):
    property_obj = get_object_or_404(Property, id=property_id)

    # ✅ Allow both landlord and agent
    if request.user != property_obj.landlord and request.user != property_obj.agent:
        messages.error(request, "You don't have permission to manage images for this property.")
        return redirect('property_detail', property_id=property_obj.id)

    if request.method == 'POST':
        if 'image' in request.FILES:
            image = request.FILES['image']
            is_primary = not property_obj.images.exists()
            PropertyImage.objects.create(property=property_obj, image=image, is_primary=is_primary)
            messages.success(request, "Image added successfully.")

        elif delete_id := request.POST.get('delete_image'):
            PropertyImage.objects.filter(id=delete_id, property=property_obj).delete()
            messages.success(request, "Image deleted.")

        elif set_primary_id := request.POST.get('set_primary'):
            property_obj.images.update(is_primary=False)
            PropertyImage.objects.filter(id=set_primary_id).update(is_primary=True)
            messages.success(request, "Primary image updated.")

        return redirect('manage_property_images', property_id=property_obj.id)

    return render(request, 'properties/manage_images.html', {
        'property': property_obj,
        'images': property_obj.images.all()
    })


# ========================== REVIEWS & SAVED ==========================
@login_required
def add_review(request, property_id):
    prop = get_object_or_404(Property, id=property_id)
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        if rating and comment:
            PropertyReview.objects.create(
                property=prop,
                tenant=request.user,
                rating=int(rating),
                comment=comment,
                is_approved=False
            )
            messages.success(request, "Review submitted. It will appear after approval.")
        else:
            messages.error(request, "Rating and comment are required.")
    return redirect('property_detail', pk=property_id)


@login_required
def toggle_save_property(request, property_id):
    if request.user.role != 'tenant':
        return JsonResponse({'error': 'Only tenants can save properties'}, status=403)

    prop = get_object_or_404(Property, id=property_id)
    _, created = SavedProperty.objects.get_or_create(tenant=request.user, property=prop)

    return JsonResponse({'saved': created})


# ========================== VIEWINGS ==========================
@login_required
def request_viewing(request, property_id):
    prop = get_object_or_404(Property, id=property_id)
    if request.user.role != 'tenant':
        messages.error(request, "Only tenants can request viewings.")
        return redirect('property_detail', pk=property_id)

    if request.method == 'POST':
        form = ViewingAppointmentForm(request.POST, property=prop)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.tenant = request.user
            appointment.property = prop
            appointment.save()

            Notification.objects.create(
                user=prop.landlord,
                title="New Viewing Request",
                message=f"{request.user.get_full_name() or request.user.username} requested a viewing for {prop.title}.",
                link=f"/property/{prop.id}/"
            )
            messages.success(request, "Viewing request sent successfully.")
            return redirect('property_detail', pk=property_id)
    else:
        form = ViewingAppointmentForm(property=prop, initial={'unit': request.GET.get('unit')})

    return render(request, 'properties/request_viewing.html', {'property': prop, 'form': form})


from django.db.models import Q
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import ViewingAppointment

@login_required
def manage_viewings(request):
    # Fetch viewings for properties owned or managed by the current user
    viewings = ViewingAppointment.objects.filter(
        Q(property__landlord=request.user) | Q(property__agent=request.user)
    ).select_related(
        'property',
        'property__landlord',   # for the owner
        'property__agent',      # for the agent (if any)
        'unit',
        'tenant',
        'unit',
    ).order_by('-created_at')

    context = {
        'appointments': viewings,   # ✅ matches the template
        'pending_count': viewings.filter(status='pending').count(),
        'confirmed_count': viewings.filter(status='confirmed').count(),
        'cancelled_count': viewings.filter(status='cancelled').count(),
        'completed_count': viewings.filter(status='completed').count(),
    }
    return render(request, 'properties/manage_viewings.html', context)


@login_required
def update_appointment_status(request, appointment_id, status):
    if request.user.role != 'landlord':
        messages.error(request, "Unauthorized.")
        return redirect('dashboard')

    appointment = get_object_or_404(ViewingAppointment, id=appointment_id, property__landlord=request.user)

    if status in ['confirmed', 'cancelled']:
        appointment.status = status
        appointment.save()

        # Email notification
        send_mail(
            subject=f"Viewing {status} for {appointment.property.title}",
            message=f"Your viewing request for {appointment.property.title} on {appointment.preferred_date} has been {status}.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[appointment.tenant.email],
            fail_silently=True,
        )

        # In-app notification
        Notification.objects.create(
            user=appointment.tenant,
            title=f"Viewing {status}",
            message=f"Your viewing for {appointment.property.title} has been {status}.",
            link=f"/property/{appointment.property.id}/"
        )
        messages.success(request, f"Appointment {status}.")
    return redirect('manage_viewings')


@login_required
def cancel_appointment(request, appointment_id):
    appointment = get_object_or_404(ViewingAppointment, id=appointment_id, tenant=request.user)
    if appointment.status == 'pending':
        appointment.status = 'cancelled'
        appointment.save()
        messages.success(request, "Appointment cancelled.")
    else:
        messages.error(request, "Only pending appointments can be cancelled.")
    return redirect('dashboard')


# ========================== CHAT ==========================
@login_required
def chat_detail(request, property_id, user_id=None):
    prop = get_object_or_404(Property, id=property_id)

    if request.user.role == 'tenant':
        other_user = prop.landlord
    else:
        other_user = get_object_or_404(User, id=user_id, role='tenant')

    chat_messages = ChatMessage.objects.filter(
        property=prop,
        sender__in=[request.user, other_user],
        receiver__in=[request.user, other_user]
    ).order_by('created_at')

    # Mark as read
    chat_messages.filter(receiver=request.user, is_read=False).update(is_read=True)

    context = {
        'property': prop,
        'chat_messages': chat_messages,
        'other_user': other_user,
        'ws_url': f"/ws/chat/{prop.id}/{other_user.id}/",
    }
    return render(request, 'properties/chat_detail.html', context)


@login_required
def chat_list(request):
    messages_qs = ChatMessage.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user)
    ).order_by('-created_at')

    seen = set()
    conversations = []
    for msg in messages_qs:
        other = msg.sender if msg.receiver == request.user else msg.receiver
        key = (msg.property_id, other.id)
        if key not in seen:
            seen.add(key)
            conversations.append({
                'property': msg.property,
                'other_user': other,
                'last_message': msg.message[:60],
                'last_message_time': msg.created_at,
            })
    return render(request, 'properties/chat_list.html', {'conversations': conversations})


# ========================== NOTIFICATIONS ==========================
@login_required
def unread_message_count(request):
    count = ChatMessage.objects.filter(receiver=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})


@login_required
def unread_notifications_count(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})


@login_required
def notifications_list(request):
    notifications = request.user.notifications.order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()
    read_count = notifications.filter(is_read=True).count()

    # ✅ Do NOT mark all as read here – let the user click to mark individually
    return render(request, 'properties/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'read_count': read_count,
    })


@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'ok', 'unread_count': request.user.notifications.filter(is_read=False).count()})


@login_required
def delete_notification(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.delete()
    return redirect('notification_list')   


@login_required
def mark_all_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('notification_list')   

@login_required
def delete_all_notifications(request):
    request.user.notifications.all().delete()
    return redirect('notification_list')  


# ========================== FAVORITES & COMPARE ==========================
@login_required
def add_favorite_estate(request):
    if request.method == 'POST':
        estate = request.POST.get('estate')
        town = request.POST.get('town')
        if estate and town:
            FavoriteEstate.objects.get_or_create(
                tenant=request.user, estate=estate, town=town,
                county=request.POST.get('county', '')
            )
            messages.success(request, f"{estate}, {town} added to favorites.")
        else:
            messages.error(request, "Estate and town are required.")
    return redirect('dashboard')


@login_required
def remove_favorite_estate(request, estate_id):
    FavoriteEstate.objects.filter(id=estate_id, tenant=request.user).delete()
    messages.success(request, "Favorite removed.")
    return redirect('dashboard')


# ========================== COMPARE ==========================
@login_required
def compare(request):
    unit_ids = request.session.get('compare_list', [])
    units = Unit.objects.filter(id__in=unit_ids).select_related(
        'property', 'property__landlord'
    ).prefetch_related('property__images')

    # Order units as they appear in the session
    order = {str(id): i for i, id in enumerate(unit_ids)}
    units = sorted(units, key=lambda u: order.get(str(u.id), 999))

    # Compute scores and display titles
    for unit in units:
        prop = unit.property
        unit.display_title = f"{unit.get_unit_type_display()} #{unit.unit_number or 'N/A'} – {prop.title}"

        rent_score = 100 - min(100, float(unit.monthly_rent) / 1000)
        amenity_score = 0
        if unit.furnished: amenity_score += 10
        if unit.has_water: amenity_score += 5
        if unit.has_electricity: amenity_score += 5
        if unit.has_parking: amenity_score += 10
        if unit.has_security: amenity_score += 5

        prop_bonus = 0
        if prop.is_verified: prop_bonus += 15
        if prop.is_featured: prop_bonus += 10

        unit.compare_score = rent_score + amenity_score + prop_bonus

    # Recommendation logic
    recommendation = None
    if len(units) >= 2:
        best = max(units, key=lambda u: u.compare_score)
        cheapest = min(units, key=lambda u: u.monthly_rent)

        for unit in units:
            unit.value_score = (unit.compare_score / (float(unit.monthly_rent) / 100)) if unit.monthly_rent > 0 else 0
        best_value = max(units, key=lambda u: u.value_score)

        # Build reasons for each recommendation
        # Best Overall reason
        best_reason = f"Highest overall score ({best.compare_score:.0f} pts) – combines affordable rent, amenities, and a verified property."
        # Cheapest reason
        cheapest_reason = f"Lowest monthly rent at KES {cheapest.monthly_rent:.0f} – saves you money every month."
        # Best Value reason
        value_reason = f"Best price‑to‑features ratio – offers {len([a for a in [best_value.furnished, best_value.has_water, best_value.has_electricity, best_value.has_parking, best_value.has_security] if a])} amenities at a competitive rent."

        recommendation = {
            'best_overall': {'unit': best, 'reason': best_reason},
            'cheapest': {'unit': cheapest, 'reason': cheapest_reason},
            'best_value': {'unit': best_value, 'reason': value_reason},
        }

    context = {
        'units': units,
        'recommendation': recommendation,
    }
    return render(request, 'properties/compare.html', context)

# add_to_compare
@login_required
def add_to_compare(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)

    compare_list = request.session.get('compare_list', [])
    if unit_id in compare_list:
        messages.warning(request, f"Unit '{unit.unit_number}' is already in your compare list.")
    else:
        if len(compare_list) >= 4:
            messages.error(request, "You can compare up to 4 units.")
        else:
            compare_list.append(unit_id)
            request.session['compare_list'] = compare_list
            request.session.modified = True
            messages.success(request, f"Unit '{unit.unit_number}' added to compare.")
    return redirect('compare')

# remove_from_compare
def remove_from_compare(request, unit_id):
    compare_list = request.session.get('compare_list', [])
    if unit_id in compare_list:
        compare_list.remove(unit_id)
        request.session['compare_list'] = compare_list
        request.session.modified = True
        messages.success(request, "Unit removed from compare.")
    return redirect('compare')

# ========================== SCAM REPORT ==========================
@login_required
def report_scam(request, property_id=None):
    property_obj = get_object_or_404(Property, id=property_id) if property_id else None

    if request.method == 'POST':
        description = request.POST.get('description')
        evidence = request.FILES.get('evidence')

        if not description:
            messages.error(request, "Description is required.")
        else:
            ScamReport.objects.create(
                reported_by=request.user,
                property=property_obj,
                landlord=request.POST.get('landlord_id') and get_object_or_404(User, id=request.POST.get('landlord_id')),
                description=description,
                evidence=evidence
            )
            messages.success(request, "Report submitted. Our team will review it.")
            return redirect('dashboard')

    return render(request, 'properties/report_scam.html', {'property': property_obj})


# ========================== QR CODE ==========================
@login_required
def appointment_qr(request, appointment_id):
    appointment = get_object_or_404(ViewingAppointment, id=appointment_id)
    if request.user not in [appointment.tenant, appointment.property.landlord]:
        return HttpResponse("Unauthorized", status=403)

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
                       box_size=10, border=4)
    qr.add_data(request.build_absolute_uri(f"/appointment/checkin/{appointment.id}/"))
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


@login_required
def qr_checkin(request, appointment_id):
    appointment = get_object_or_404(ViewingAppointment, id=appointment_id)
    if request.user not in [appointment.tenant, appointment.property.landlord]:
        messages.error(request, "Unauthorized.")
        return redirect('dashboard')

    if appointment.status != 'confirmed':
        messages.error(request, "Appointment not confirmed.")
        return redirect('dashboard')

    if appointment.checked_in:
        messages.info(request, "Already checked in.")
    else:
        appointment.checked_in = True
        appointment.checked_in_at = timezone.now()
        appointment.save()
        messages.success(request, "Check-in successful!")

    return redirect('dashboard')

@cache_page(60 * 60 * 24)  # Cache for 24 hours
@vary_on_cookie            # ✨ CRITICAL: Keeps public traffic and authenticated states separated in cache memory
def how_it_works(request):
    return render(request, 'static_pages/how_it_works.html')


@cache_page(60 * 60 * 24)
@vary_on_cookie            # Apply this to safety tips too if it uses the same base layout!
def safety_tips(request):
    """Simple static page - cached safely per session state"""
    return render(request, 'static_pages/safety_tips.html')