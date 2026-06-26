import phonenumbers

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import Profile, UserProfile, IndianState, Order, OTP, Category, Subcategory, ContactMessage, Quotation

class CustomUserCreationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30, required=True, label='First Name *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'})
    )
    last_name = forms.CharField(
        max_length=30, required=False, label='Last Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name (Optional)'})
    )
    age = forms.IntegerField(required=False, min_value=13, label='Age')
    phone_number = forms.CharField(max_length=15, required=True, label='Phone Number')
    address = forms.CharField(widget=forms.Textarea, required=False, label='Address')
    state = forms.ChoiceField(choices=IndianState.choices, required=False, label='State')
    verification_method = forms.ChoiceField(
        choices=Profile.VERIFICATION_METHOD_CHOICES,
        required=True,
        label='Verify Account Using',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='email',
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'password1', 'password2', 'age', 'phone_number', 'address', 'state', 'verification_method')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['phone_number'].required = True
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Sign Up', css_class='btn btn-success btn-lg w-100'))

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email address is already registered.')
        return email

    def clean_phone_number(self):
        raw_phone = self.cleaned_data.get('phone_number', '').strip()
        try:
            parsed = phonenumbers.parse(raw_phone, 'IN')
            if not phonenumbers.is_valid_number(parsed):
                raise forms.ValidationError('Enter a valid phone number.')
            normalized = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            if Profile.objects.filter(phone_number=normalized).exists():
                raise forms.ValidationError('This phone number is already in use.')
            if UserProfile.objects.filter(phone_number=normalized).exists():
                raise forms.ValidationError('This phone number is already in use.')
            return normalized
        except phonenumbers.NumberParseException:
            raise forms.ValidationError('Enter a valid phone number.')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            user.save()
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.age = self.cleaned_data.get('age')
            profile.phone_number = self.cleaned_data.get('phone_number')
            profile.address = self.cleaned_data.get('address')
            profile.state = self.cleaned_data.get('state')
            profile.save()
        return user

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('username', 'email')

class ProfileForm(forms.ModelForm):
    """Form for editing user profile including User model fields and UserProfile fields."""
    first_name = forms.CharField(
        max_length=30, required=False, label='First Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'})
    )
    last_name = forms.CharField(
        max_length=30, required=False, label='Last Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'})
    )
    email = forms.EmailField(
        required=False, label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control', 'placeholder': 'Email address',
            'readonly': 'readonly', 'style': 'background-color: #e9ecef; cursor: not-allowed;',
        })
    )

    class Meta:
        model = UserProfile
        fields = ['phone_number', 'profile_image', 'address', 'state',
                  'current_address', 'latitude', 'longitude', 'city',
                  'postal_code', 'country', 'address_source']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Delivery address'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91XXXXXXXXXX'}),
            'state': forms.Select(attrs={'class': 'form-control'}),
            'profile_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'current_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Current location address', 'readonly': 'readonly'}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
            'city': forms.HiddenInput(),
            'postal_code': forms.HiddenInput(),
            'country': forms.HiddenInput(),
            'address_source': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Update Profile', css_class='btn btn-primary btn-lg w-100'))

    def clean_phone_number(self):
        raw_phone = self.cleaned_data.get('phone_number', '').strip()
        if not raw_phone:
            return raw_phone
        try:
            parsed = phonenumbers.parse(raw_phone, 'IN')
            if not phonenumbers.is_valid_number(parsed):
                raise forms.ValidationError('Enter a valid phone number.')
            normalized = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            existing = UserProfile.objects.filter(phone_number=normalized).exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError('This phone number is already in use.')
            return normalized
        except phonenumbers.NumberParseException:
            raise forms.ValidationError('Enter a valid phone number.')

    def clean_profile_image(self):
        image = self.cleaned_data.get('profile_image')
        if image:
            if hasattr(image, 'size') and image.size > 5 * 1024 * 1024:
                raise forms.ValidationError('Profile image must be less than 5MB.')
            if hasattr(image, 'content_type'):
                allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
                if image.content_type not in allowed_types:
                    raise forms.ValidationError('Only JPEG, PNG, WebP, and GIF images are allowed.')
        return image

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            user = profile.user
            user.first_name = self.cleaned_data.get('first_name', '')
            user.last_name = self.cleaned_data.get('last_name', '')
            user.save()
            profile.save()
        return profile

class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Change Password', css_class='btn btn-success btn-lg w-100'))

class CheckoutShippingForm(forms.ModelForm):
    full_name = forms.CharField(
        required=True,
        label='Full Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'})
    )
    email = forms.EmailField(
        required=False,
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'})
    )
    address_line2 = forms.CharField(
        required=False,
        label='House / Flat / Landmark',
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Apt, suite, floor, landmark (optional)'}),
    )
    country = forms.CharField(
        required=True,
        label='Country',
        initial='India',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'})
    )
    delivery_instructions = forms.CharField(
        required=False,
        label='Delivery Instructions',
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Leave delivery instructions for the courier'}),
    )
    latitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput())
    longitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput())
    # Override state as a plain CharField (not a ChoiceField) so that unrecognized
    # values from the "Use Current Location" feature (e.g. the string "undefined")
    # are accepted at the field level and can be normalized in clean_state().
    state = forms.CharField(
        required=False,
        label='State',
        widget=forms.Select(attrs={'class': 'form-control'}, choices=[('', '--- Select State ---')] + list(IndianState.choices))
    )

    class Meta:
        model = Order
        fields = ['address_line1', 'city', 'state', 'pincode', 'phone', 'latitude', 'longitude']
        widgets = {
            'address_line1': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Street address, house number'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PIN code (e.g., 400001)', 'maxlength': '10'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number (up to 15 characters)', 'maxlength': '15'}),
        }
        labels = {
            'address_line1': 'Street Address',
            'city': 'City',
            'state': 'State',
            'pincode': 'Postal Code',
            'phone': 'Phone',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'

    def clean_state(self):
        state = self.cleaned_data.get('state')
        if state in ('undefined', '', None):
            return ''
        return state

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '')
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) > 15:
            raise forms.ValidationError('Phone number must have no more than 15 digits in total.')
        return phone


class PhoneSignupForm(forms.Form):
    phone = forms.CharField(
        max_length=20,
        label='Phone number',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '+91XXXXXXXXXX',
            'autocomplete': 'tel',
        })
    )

    def clean_phone(self):
        raw_phone = self.cleaned_data.get('phone', '').strip()
        try:
            parsed = phonenumbers.parse(raw_phone, 'IN')
            if not phonenumbers.is_valid_number(parsed):
                raise forms.ValidationError('Enter a valid phone number.')
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise forms.ValidationError('Enter a valid phone number.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'
        self.helper.add_input(Submit('submit', 'Send OTP', css_class='btn btn-success btn-lg w-100'))


class PhoneLoginForm(forms.Form):
    phone = forms.CharField(
        max_length=20,
        label='Phone number',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '+91XXXXXXXXXX',
            'autocomplete': 'tel',
        })
    )

    def clean_phone(self):
        raw_phone = self.cleaned_data.get('phone', '').strip()
        try:
            parsed = phonenumbers.parse(raw_phone, 'IN')
            if not phonenumbers.is_valid_number(parsed):
                raise forms.ValidationError('Enter a valid phone number.')
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise forms.ValidationError('Enter a valid phone number.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'
        self.helper.add_input(Submit('submit', 'Send OTP', css_class='btn btn-success btn-lg w-100'))


class PhoneOTPForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        label='Enter OTP',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-center fw-bold fs-4',
            'placeholder': '000000',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'
        self.helper.add_input(Submit('submit', 'Verify OTP', css_class='btn btn-success btn-lg w-100 py-3 fs-5'))

    def clean_otp(self):
        otp = self.cleaned_data.get('otp', '').strip()
        if not otp.isdigit():
            raise forms.ValidationError('OTP must contain only numbers.')
        return otp


class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6, 
        min_length=6, 
        label='Enter 6-digit verification code',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-center fw-bold fs-4',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'autocomplete': 'one-time-code',
            'placeholder': '000000'
        })
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'
        self.helper.add_input(Submit('submit', 'Verify OTP', css_class='btn btn-success btn-lg w-100 py-3 fs-5'))

    def clean(self):
        cleaned_data = super().clean()
        otp_input = cleaned_data.get('otp')
        
        if otp_input:
            latest_otp = OTP.objects.filter(
                user=self.user, 
                is_latest=True
            ).first()
            
            if not latest_otp:
                raise forms.ValidationError('No OTP found. Please request a new one.')

            if latest_otp.is_expired:
                latest_otp.attempts += 1
                latest_otp.save()
                raise forms.ValidationError('OTP expired. Please resend a new code.')

            if latest_otp.otp != otp_input:
                latest_otp.attempts += 1
                latest_otp.save()
                remaining = max(0, latest_otp.max_attempts - latest_otp.attempts)
                raise forms.ValidationError(f'Invalid OTP. You have {remaining} attempt(s) left.')

            if not latest_otp.is_valid:
                raise forms.ValidationError('This OTP is no longer valid. Please resend a new code.')

        return cleaned_data


class ProductAdminForm(forms.ModelForm):
    """Form for Product admin that filters subcategories by selected category."""

    class Meta:
        from .models import Product
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing an existing product with a category, limit subcategory choices
        if self.instance and self.instance.pk and self.instance.category:
            self.fields['subcategory'].queryset = Subcategory.objects.filter(
                category=self.instance.category
            )
        else:
            # New product: start with empty queryset until category is chosen via JS
            self.fields['subcategory'].queryset = Subcategory.objects.none()

        # When category is submitted, filter subcategory accordingly
        if 'category' in self.data:
            try:
                category_id = int(self.data.get('category'))
                self.fields['subcategory'].queryset = Subcategory.objects.filter(
                    category_id=category_id
                )
            except (ValueError, TypeError):
                pass


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': ' ', 'id': 'name',
                'autocomplete': 'name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': ' ', 'id': 'email',
                'autocomplete': 'email',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': ' ', 'id': 'phone',
                'autocomplete': 'tel',
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': ' ', 'id': 'subject',
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control', 'placeholder': ' ', 'id': 'message',
                'rows': 5,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'
        self.helper.form_id = 'contactForm'

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Full name is required.')
        if len(name) < 2:
            raise forms.ValidationError('Name must be at least 2 characters.')
        return name

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError('Email address is required.')
        import re
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            raise forms.ValidationError('Please enter a valid email address.')
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            import re
            digits = re.sub(r'\D', '', phone)
            if len(digits) < 7 or len(digits) > 15:
                raise forms.ValidationError('Please enter a valid phone number.')
        return phone

    def clean_subject(self):
        subject = self.cleaned_data.get('subject', '').strip()
        if not subject:
            raise forms.ValidationError('Subject is required.')
        if len(subject) < 3:
            raise forms.ValidationError('Subject must be at least 3 characters.')
        return subject

    def clean_message(self):
        message = self.cleaned_data.get('message', '').strip()
        if not message:
            raise forms.ValidationError('Message is required.')
        if len(message) < 10:
            raise forms.ValidationError('Message must be at least 10 characters.')
        return message


class QuotationShippingForm(forms.ModelForm):
    full_name = forms.CharField(
        required=True,
        label='Full Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'})
    )
    email = forms.EmailField(
        required=False,
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'})
    )
    address_line2 = forms.CharField(
        required=False,
        label='House / Flat / Landmark',
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Apt, suite, floor, landmark (optional)'}),
    )
    state = forms.CharField(
        required=False,
        label='State',
        widget=forms.Select(attrs={'class': 'form-control'}, choices=[('', '--- Select State ---')] + list(IndianState.choices))
    )

    class Meta:
        model = Quotation
        fields = ['full_name', 'email', 'phone', 'address_line1', 'address_line2', 'city', 'state', 'pincode', 'delivery_notes']
        widgets = {
            'address_line1': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Street address, house number'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PIN code (e.g., 400001)', 'maxlength': '10'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number (up to 15 characters)', 'maxlength': '15'}),
            'delivery_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Leave delivery notes/instructions'}),
        }
        labels = {
            'address_line1': 'Street Address',
            'city': 'City',
            'state': 'State',
            'pincode': 'Postal Code',
            'phone': 'Phone',
            'delivery_notes': 'Delivery Notes',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'POST'


