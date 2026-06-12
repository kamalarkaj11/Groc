import phonenumbers

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import Profile, UserProfile, IndianState, Order, OTP, Category, Subcategory

class CustomUserCreationForm(UserCreationForm):
    age = forms.IntegerField(required=False, min_value=13, label='Age')
    phone_number = forms.CharField(max_length=15, required=True, label='Phone Number')
    address = forms.CharField(widget=forms.Textarea, required=False, label='Address')
    state = forms.ChoiceField(choices=IndianState.choices, required=False, label='State')


    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2', 'age', 'phone_number', 'address', 'state')

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
            return normalized
        except phonenumbers.NumberParseException:
            raise forms.ValidationError('Enter a valid phone number.')

    def save(self, commit=True):
        user = super().save(commit=False)
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
    class Meta:
        model = UserProfile
        fields = ['age', 'phone_number', 'address', 'state', 'profile_image']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Update Profile', css_class='btn btn-primary btn-lg w-100'))

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

    class Meta:
        model = Order
        fields = ['address_line1', 'city', 'state', 'pincode', 'phone', 'latitude', 'longitude']
        widgets = {
            'address_line1': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Street address, house number'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.Select(attrs={'class': 'form-control'}),
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
        if state == 'undefined':
            return ''
        return state

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '')
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) > 15:
            raise forms.ValidationError('Phone number must have no more than 15 digits in total.')
        return phone

    def clean_state(self):
        state = self.cleaned_data.get('state')
        if state == 'undefined':
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

