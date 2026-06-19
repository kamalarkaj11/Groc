from django import forms
from .models import APIKey, APIKeyCategory, APIKeyStatus


class APIKeyForm(forms.ModelForm):
    """Form for creating and editing API keys."""
    api_key = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter API key',
            'autocomplete': 'off',
        }),
        help_text='The API key will be encrypted before storage.',
    )

    class Meta:
        model = APIKey
        fields = ['name', 'provider', 'base_url', 'category', 'status']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Google Maps API',
            }),
            'provider': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Google',
            }),
            'base_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://api.example.com/v1',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.get('instance', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['api_key'].required = False
            self.fields['api_key'].widget.attrs['placeholder'] = 'Leave blank to keep current key'

    def clean_api_key(self):
        api_key = self.cleaned_data.get('api_key')
        if not api_key and self.instance and self.instance.pk:
            return None
        if not api_key:
            raise forms.ValidationError('API key is required.')
        return api_key

    def save(self, commit=True):
        instance = super().save(commit=False)
        api_key = self.cleaned_data.get('api_key')
        if api_key:
            instance.set_api_key(api_key)
        if commit:
            instance.save()
        return instance