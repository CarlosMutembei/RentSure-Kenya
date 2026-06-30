from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import DeviceFingerprint
import json

@csrf_exempt
@require_POST
@login_required
def device_fingerprint(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    fingerprint = data.get('fingerprint')
    user_agent = data.get('user_agent', '')

    if not fingerprint:
        return JsonResponse({'status': 'error', 'message': 'fingerprint required'}, status=400)

    # Clean integration mapping directly to your model fields
    DeviceFingerprint.objects.update_or_create(
        fingerprint=fingerprint,
        defaults={
            'user': request.user,
            'user_agent': user_agent,
            # ✅ Fixed: Changed from 'last_active' to match 'last_seen' in models.py
        }
    )

    return JsonResponse({'status': 'ok'})