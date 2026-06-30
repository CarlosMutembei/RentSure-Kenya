from django import forms
from users.models import User
from .models import Property, ViewingAppointment, Unit


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'address_text', 'town', 'estate',
            'video', 'rules',
            'wifi', 'pets_allowed',
            'service_charge',
            'has_water', 'has_electricity', 'has_parking', 'has_security',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full border p-2 rounded',
                'placeholder': 'e.g., Cozy 2BR in Kilimani'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full border p-2 rounded',
                'rows': 4,
                'placeholder': 'Describe the property, amenities, nearby facilities...'
            }),
            'address_text': forms.TextInput(attrs={
                'class': 'w-full border p-2 rounded',
                'placeholder': 'e.g., Next to Quickmart, Kimathi Street'
            }),
            'town': forms.TextInput(attrs={
                'class': 'w-full border p-2 rounded',
                'placeholder': 'Nairobi, Mombasa, Kisumu...'
            }),
            'estate': forms.TextInput(attrs={
                'class': 'w-full border p-2 rounded',
                'placeholder': 'e.g., Westlands, Kilimani, Nyali'
            }),
            'video': forms.ClearableFileInput(attrs={
                'class': 'w-full border p-2 rounded'
            }),
            'rules': forms.Textarea(attrs={
                'class': 'w-full border p-2 rounded',
                'rows': 4,
                'placeholder': 'e.g., No smoking, quiet hours after 10pm, pets allowed with deposit...'
            }),
            'wifi': forms.CheckboxInput(attrs={'class': 'mr-2'}),
            'pets_allowed': forms.CheckboxInput(attrs={'class': 'mr-2'}),
            'service_charge': forms.NumberInput(attrs={
                'class': 'w-full border p-2 rounded',
                'placeholder': 'e.g. 1500'
            }),
            'has_water': forms.CheckboxInput(attrs={'class': 'mr-2'}),
            'has_electricity': forms.CheckboxInput(attrs={'class': 'mr-2'}),
            'has_parking': forms.CheckboxInput(attrs={'class': 'mr-2'}),
            'has_security': forms.CheckboxInput(attrs={'class': 'mr-2'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter agent choices depending on the current user
        self.fields['agent'] = forms.ModelChoiceField(
            queryset=User.objects.filter(role='agent'),
            required=False,
            widget=forms.Select(attrs={'class': 'w-full border p-2 rounded'})
        )

        if user and user.role == 'landlord':
            self.fields['agent'].required = False

        elif user and user.role == 'agent':
            # Hide agent field for agents since the view assigns it automatically
            self.fields['agent'].widget = forms.HiddenInput()
            self.fields['agent'].required = False
            self.fields['agent'].queryset = User.objects.filter(id=user.id)

        else:
            self.fields['agent'].queryset = User.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        agent = cleaned_data.get('agent')

        # Optional place to add extra validation rules
        if agent and agent.role != 'agent':
            self.add_error('agent', 'Selected user must be an agent.')

        return cleaned_data


class ViewingAppointmentForm(forms.ModelForm):
    class Meta:
        model = ViewingAppointment
        fields = ['unit', 'preferred_date', 'preferred_time', 'message']
        widgets = {
            'unit': forms.Select(attrs={'class': 'w-full border rounded-xl p-3 focus:ring-2 focus:ring-blue-500'}),
            'preferred_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full border rounded-xl p-3 focus:ring-2 focus:ring-blue-500'}),
            'preferred_time': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full border rounded-xl p-3 focus:ring-2 focus:ring-blue-500'}),
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Any special requests? (optional)', 'class': 'w-full border rounded-xl p-3 focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        property_obj = kwargs.pop('property', None)
        super().__init__(*args, **kwargs)
        self.fields['message'].required = False

        # Limit unit choices to the selected property
        if property_obj:
            self.fields['unit'].queryset = property_obj.units.all()
        else:
            self.fields['unit'].queryset = Unit.objects.none()