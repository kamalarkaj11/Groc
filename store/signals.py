"""
Django signals for login activity tracking and notifications.
"""
import logging
import random
from datetime import timedelta

from django.contrib.auth import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

from .models import LoginActivity, Profile, UserProfile, OTP
from .login_utils import create_login_activity, get_user_agent_info, get_client_ip
from store.tasks import send_login_email_task, send_login_sms_task

logger = logging.getLogger(__name__)


def generate_otp():
    """Generate a 6-digit OTP code."""
    return f"{random.randint(0, 999999):06d}"


def create_otp(user):
    """
    Create a new OTP for the given user.
    Invalidates any previous latest OTPs.
    """
    OTP.objects.filter(user=user, is_latest=True).update(is_latest=False)
    otp_code = generate_otp()
    expires_at = timezone.now() + timedelta(minutes=5)
    otp = OTP.objects.create(
        user=user,
        otp=otp_code,
        expires_at=expires_at,
        is_latest=True,
    )
    return otp


def send_otp_email(user, otp):
    """
    Send an OTP verification email to the user.
    """
    subject = 'Your Verification Code - GroceryHub'
    html_message = render_to_string('emails/otp_email.html', {
        'user': user,
        'otp': otp.otp,
        'expires_in': '5 minutes',
        'purpose': 'verification'
    })
    plain_message = strip_tags(html_message)
    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )


def generate_and_send_otp(user):
    """
    Generate a new OTP and send it to the user via email.
    Returns the created OTP object.
    """
    otp = create_otp(user)
    send_otp_email(user, otp)
    return otp


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    Signal handler for successful user login.
    Creates LoginActivity record and dispatches email/SMS notifications.
    """
    try:
        # Detect login method
        login_method = 'password'  # default
        if hasattr(request, 'session'):
            if request.session.get('phone_for_otp') or request.session.get('signup_phone'):
                login_method = 'otp'
        
        # Create login activity record
        login_activity = create_login_activity(user, request, login_method=login_method)
        
        # Prepare request data for async tasks
        request_data = {
            'HTTP_USER_AGENT': request.META.get('HTTP_USER_AGENT', ''),
        }
        
        # Dispatch email notification asynchronously
        try:
            send_login_email_task.delay(
                user_id=user.id,
                login_activity_id=login_activity.id,
                request_data=request_data
            )
            logger.info('Login email task dispatched for user %s', user.id)
        except Exception as exc:
            logger.error('Failed to dispatch login email task for user %s: %s', user.id, exc, exc_info=True)
        
        # Dispatch SMS notification asynchronously
        try:
            send_login_sms_task.delay(
                user_id=user.id,
                login_activity_id=login_activity.id,
                request_data=request_data
            )
            logger.info('Login SMS task dispatched for user %s', user.id)
        except Exception as exc:
            logger.error('Failed to dispatch login SMS task for user %s: %s', user.id, exc, exc_info=True)
        
        # Create in-app notification
        try:
            from .models import Notification
            ua_info = get_user_agent_info(request)
            city = login_activity.city or 'Unknown'
            device = ua_info.get('device', 'Unknown')
            
            Notification.objects.create(
                user=user,
                title='Successful login detected',
                message=f'Successful login detected from {city} on {device}.',
                notification_type='auth',
            )
            logger.info('In-app notification created for user %s', user.id)
        except Exception as exc:
            logger.error('Failed to create in-app notification for user %s: %s', user.id, exc, exc_info=True)
        
        logger.info(
            'Login signal processed: user=%s, method=%s, activity_id=%s',
            user.username, login_method, login_activity.id
        )
        
    except Exception as exc:
        logger.error('Error in on_user_logged_in signal for user %s: %s', user.id, exc, exc_info=True)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """
    Signal handler for user logout.
    Logs the logout event.
    """
    if user:
        logger.info('User logged out: %s', user.username)