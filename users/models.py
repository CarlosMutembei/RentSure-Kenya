from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField, settings




class User(AbstractUser):
    ROLE_CHOICES = (
    ('tenant', 'Tenant'),
    ('landlord', 'Landlord'),
    ('agent', 'Agent'),
    ('admin', 'Admin'),
)
    phone = PhoneNumberField(unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='tenant')
    id_number = models.CharField(max_length=20, blank=True, null=True)
    # is_verified = models.BooleanField(default=False)
    trust_score = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    
    # Inside User model (add if missing)
    kyc_id_number = models.CharField(max_length=20, blank=True, null=True)
    kyc_kra_pin = models.CharField(max_length=11, blank=True, null=True)
    kyc_document = models.FileField(upload_to='kyc_documents/', blank=True, null=True)  # ID or title deed
    kyc_status = models.CharField(max_length=20, choices=[('pending','Pending'),('verified','Verified'),('rejected','Rejected')], default='', blank=True)
    kyc_submitted_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    
    default_town = models.CharField(max_length=100, blank=True, null=True)
    default_estate = models.CharField(max_length=100, blank=True, null=True)
    default_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    default_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    
    # Landlord verification fields
    kra_pin = models.CharField(max_length=11, blank=True, null=True)
    utility_bill = models.FileField(upload_to='verify/', blank=True, null=True)
    
    title_deed = models.FileField(upload_to='verification/', blank=True, null=True)
    # verification_status = models.CharField(
    #     max_length=20, choices=[('pending','Pending'),
    #                             ('verified','Verified'),
    #                             ('rejected','Rejected')], 
    #     default='pending')
    
    def __str__(self):
        return f"{self.username} ({self.phone})"

class Testimonial(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100)
    content = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.created_at.date()}"
    
class AppLaunchLead(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
    
