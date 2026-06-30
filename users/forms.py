from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from security.models import BlacklistEntry

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=True)
    role = forms.ChoiceField(choices=[('tenant','Tenant'),('landlord','Landlord'),('agent','Agent')])
    profile_photo = forms.ImageField(required=False, label="Profile Photo")

    class Meta:
        model = User
        fields = ['username', 'email', 'phone', 'role', 'profile_photo', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Add Tailwind classes to each visible field
            if field_name == 'profile_photo':
                field.widget.attrs.update({'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100', 'accept': 'image/*'})
            elif field_name in ['username', 'email', 'phone', 'password1', 'password2']:
                field.widget.attrs.update({'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent'})
            elif field_name == 'role':
                field.widget.attrs.update({'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg bg-white'})

    def clean(self):
        cleaned_data = super().clean()
        phone = cleaned_data.get('phone')
        id_number = cleaned_data.get('id_number')
        email = cleaned_data.get('email')

        if phone and BlacklistEntry.objects.filter(entry_type='phone', value=phone, is_active=True).exists():
            self.add_error('phone', "This phone number is blocked.")

        if id_number and BlacklistEntry.objects.filter(entry_type='id_number', value=id_number, is_active=True).exists():
            self.add_error('id_number', "This ID number is blocked.")

        if email and BlacklistEntry.objects.filter(entry_type='email', value=email, is_active=True).exists():
            self.add_error('email', "This email address is blocked.")

        return cleaned_data