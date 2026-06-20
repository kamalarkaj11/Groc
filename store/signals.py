import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import OTP

logger = logging.getLogger(__name__)

import secrets


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
        expires_at=expires_at,
    )
    return otp


def _email_config_summary():
    return {
        "host": getattr(settings, "EMAIL_HOST", None),
        "port": getattr(settings, "EMAIL_PORT", None),
        "use_tls": getattr(settings, "EMAIL_USE_TLS", None),
        "timeout": getattr(settings, "EMAIL_TIMEOUT", None),
        "from_email": getattr(settings, "DEFAULT_FROM_EMAIL", None),
    }


def send_otp_email(user, otp):
    """Send HTML email with OTP.

    Raises exceptions on failure (fail_silently=False) so the caller can show a useful UI message.
    """
    if not getattr(user, "email", None):
        raise ValueError("User email required")

    subject = "Your GroceryHub Verification Code"
    html_message = render_to_string(
        "registration/otp_email.html",
        {
            "user": user,
            "otp": otp.otp,
            "expires_in": "5 minutes",
        },
    )
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as exc:
        cfg = _email_config_summary()
        logger.warning(
            "send_otp_email failed for user_email=%s host=%s port=%s: %s",
            user.email,
            cfg.get("host"),
            cfg.get("port"),
            exc,
            exc_info=True,
        )
        raise


def generate_and_send_otp(user):
    """Full cycle: create OTP and send email."""
    otp = create_otp(user)
    send_otp_email(user, otp)
    return otp


# ---------------------------------------------------------------------------
# Order Confirmation Signal
# ---------------------------------------------------------------------------

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order

@receiver(post_save, sender=Order)
def order_status_confirmed_handler(sender, instance, **kwargs):
    """
    Signal handler that triggers order confirmation notifications
    when the order status changes to 'confirmed'.
    
    This ensures notifications are sent automatically whenever an order
    is confirmed, whether via admin panel, API, or any other code path.
    Duplicate notifications are prevented by the notification_sent flag.
    """
    if instance.status == 'confirmed' and not instance.notification_sent:
        logger.info(
            'Order #%s status changed to "confirmed". Triggering notifications.',
            instance.id,
        )
        try:
            from .notifications import send_order_notifications
            send_order_notifications(instance.id)
        except Exception as exc:
            logger.error(
                'Failed to trigger notifications for confirmed order #%s: %s',
                instance.id, exc,
                exc_info=True,
            )


