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
from .models import Order, OrderTracking, OrderTrackingHistory, Notification

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


@receiver(post_save, sender=Order)
def order_created_tracking_handler(sender, instance, created, **kwargs):
    """
    Signal handler that automatically creates an OrderTracking record
    when a new order is created.
    """
    if created:
        try:
            OrderTracking.objects.get_or_create(order=instance)
            logger.info('Tracking record auto-created for Order #%s', instance.id)
        except Exception as exc:
            logger.error(
                'Failed to auto-create tracking for Order #%s: %s',
                instance.id, exc,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Notification Signals
# ---------------------------------------------------------------------------

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.models import User as AuthUser


def _create_notification(user, title, message, notification_type='system'):
    """Helper to create a notification for a user."""
    try:
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    except Exception as exc:
        logger.error('Failed to create notification for user %s: %s', user.id, exc)


from django.db.models.signals import pre_save


def _user_pre_save_password_tracker(sender, instance, **kwargs):
    """Store the old password hash before save so post_save can detect changes."""
    if instance.pk:
        try:
            old = AuthUser.objects.get(pk=instance.pk)
            instance._old_password_hash = old.password
        except AuthUser.DoesNotExist:
            instance._old_password_hash = instance.password
    else:
        instance._old_password_hash = instance.password


def _user_post_save_password_tracker(sender, instance, **kwargs):
    """Create a notification when the user's password is changed."""
    old_hash = getattr(instance, '_old_password_hash', None)
    if old_hash and old_hash != instance.password:
        _create_notification(
            instance,
            'Password changed',
            'Your account password was changed successfully.',
            'auth',
        )


pre_save.connect(_user_pre_save_password_tracker, sender=AuthUser)
post_save.connect(_user_post_save_password_tracker, sender=AuthUser)

from django.contrib.auth.signals import user_logged_in, user_logged_out


def on_user_logged_in(sender, request, user, **kwargs):
    _create_notification(
        user,
        'Welcome back!',
        'You logged in successfully.',
        'auth',
    )


def on_user_logged_out(sender, request, user, **kwargs):
    if user is not None:
        _create_notification(
            user,
            'Logged out',
            'You logged out successfully.',
            'auth',
        )


user_logged_in.connect(on_user_logged_in)
user_logged_out.connect(on_user_logged_out)


@receiver(post_save, sender=Order)
def order_notification_handler(sender, instance, created, **kwargs):
    """Create notifications for order lifecycle events."""
    if created:
        _create_notification(
            instance.user,
            'Order placed',
            f'Your order #{instance.id} has been placed successfully (Rs. {instance.total_amount}).',
            'order',
        )
    elif instance.status == 'confirmed' and instance.notification_sent:
        _create_notification(
            instance.user,
            'Order confirmed',
            f'Your order #{instance.id} has been confirmed.',
            'order',
        )


@receiver(post_save, sender=OrderTracking)
def tracking_status_notification_handler(sender, instance, created, **kwargs):
    """Create notifications and send email/SMS for tracking status changes."""
    if created:
        return
    old_status = getattr(instance, '_previous_status', None)
    if old_status and old_status != instance.status:
        status_messages = {
            'confirmed': 'Your order has been confirmed.',
            'packed': 'Your order has been packed and is ready for shipping.',
            'shipped': 'Your order has been shipped.',
            'out_for_delivery': 'Your order is out for delivery!',
            'delivered': 'Your order has been delivered successfully.',
            'cancelled': 'Your order has been cancelled.',
        }
        message = status_messages.get(instance.status, '')
        if message:
            _create_notification(
                instance.order.user,
                f'Order #{instance.order.id} — {instance.get_status_display()}',
                message,
                'order',
            )
            _send_tracking_status_email(instance, message)
            _send_tracking_status_sms(instance, message)


def _send_tracking_status_email(tracking, status_message):
    """Send an email notification for a tracking status change."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    order = tracking.order
    user = order.user
    customer_email = user.email
    shipping_address = getattr(order, 'shipping_address', None)
    if not customer_email and shipping_address:
        customer_email = shipping_address.email
    if not customer_email:
        return

    customer_name = user.get_full_name() or user.username
    if shipping_address and shipping_address.full_name:
        customer_name = shipping_address.full_name

    track_order_url = f"https://groc-production-6c7e.up.railway.app/track-order/{order.id}/"

    subject = f'Order #{order.id} — {tracking.get_status_display()} | GrocHub'
    html_message = render_to_string('emails/order_status_update.html', {
        'order': order,
        'customer_name': customer_name,
        'tracking_status': tracking.status,
        'status_display': tracking.get_status_display(),
        'status_message': status_message,
        'tracking_number': tracking.tracking_number,
        'delivery_partner': tracking.delivery_partner,
        'estimated_delivery_date': tracking.estimated_delivery_date,
        'track_order_url': track_order_url,
    })
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [customer_email],
            html_message=html_message,
            fail_silently=True,
        )
        logger.info('Tracking status email sent for order #%s: %s', order.id, tracking.status)
    except Exception as exc:
        logger.warning('Failed to send tracking status email for order #%s: %s', order.id, exc)


def _send_tracking_status_sms(tracking, status_message):
    """Send an SMS notification for a tracking status change."""
    from django.conf import settings

    order = tracking.order
    shipping_address = getattr(order, 'shipping_address', None)
    customer_phone = ''
    if shipping_address and shipping_address.phone:
        customer_phone = shipping_address.phone
    else:
        user_profile = getattr(order.user, 'userprofile', None)
        if user_profile and user_profile.phone_number:
            customer_phone = user_profile.phone_number

    if not customer_phone:
        return

    customer_name = order.user.get_full_name() or order.user.username
    if shipping_address and shipping_address.full_name:
        customer_name = shipping_address.full_name

    sms_text = (
        f"Hi {customer_name}! GroceryHub Order #{order.id}: "
        f"{tracking.get_status_display()}. {status_message}"
    )
    if tracking.tracking_number:
        sms_text += f" Tracking: {tracking.tracking_number}"

    try:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_PHONE_NUMBER
        if not account_sid or not auth_token or not from_number:
            return
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=sms_text, from_=from_number, to=customer_phone)
        logger.info('Tracking status SMS sent for order #%s: %s', order.id, tracking.status)
    except Exception as exc:
        logger.warning('Failed to send tracking status SMS for order #%s: %s', order.id, exc)

