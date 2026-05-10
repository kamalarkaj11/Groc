from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.utils import timezone
import secrets
import re

from .models import OTP, User

def generate_otp():
    """Generate 6-digit random numeric OTP."""
    return str(secrets.randbelow(1000000)).zfill(6)

def invalidate_old_otps(user):
    """Mark all previous OTPs as not latest."""
    OTP.objects.filter(user=user, is_latest=True).exclude(id__isnull=True).update(is_latest=False)

def create_otp(user):
    """Create new OTP, invalidate old ones."""
    otp_code = generate_otp()
    expires_at = timezone.now() + timezone.timedelta(minutes=5)
    invalidate_old_otps(user)
    otp = OTP.objects.create(
        user=user,
        otp=otp_code,
        expires_at=expires_at
    )
    return otp

def send_otp_email(user, otp):
    """Send HTML email with OTP."""
    subject = 'Your GroceryHub Verification Code'
    html_message = render_to_string('registration/otp_email.html', {
        'user': user,
        'otp': otp.otp,
        'expires_in': '5 minutes',
    })
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject,
        plain_message,
        settings.EMAIL_HOST_USER,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )

def generate_and_send_otp(user):
    """Full cycle: create OTP and send email."""
    if not user.email:
        raise ValueError("User email required")
    otp = create_otp(user)
    send_otp_email(user, otp)
    return otp

