from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from security.models import BlacklistEntry

User = get_user_model()

class BlacklistAwareBackend(ModelBackend):
    """
    Authenticates against the username/password and checks blacklist.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        # First, try to get the user using the default backend
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is None:
            return None

        # Check if the user's phone number (or email, etc.) is blacklisted
        # We'll check phone first, but you can add others if needed.
        phone = getattr(user, 'phone', None)
        if phone:
            if BlacklistEntry.objects.filter(entry_type='phone', value=phone, is_active=True).exists():
                # Optionally log the attempt
                return None  # Deny authentication

        # Optionally check email
        email = getattr(user, 'email', None)
        if email:
            if BlacklistEntry.objects.filter(entry_type='email', value=email, is_active=True).exists():
                return None

        # Optionally check ID number
        id_number = getattr(user, 'id_number', None)
        if id_number:
            if BlacklistEntry.objects.filter(entry_type='id_number', value=id_number, is_active=True).exists():
                return None

        return user