"""
Celery tasks for sending order confirmation notifications (email & SMS) and newsletter notifications.
Includes automatic retry with exponential backoff (up to 3 retries).

SAFE DELAY:
All task invocations use `safe_delay()` which catches broker connection errors
and falls back to executing the task synchronously.
"""

import logging
from datetime import timedelta

from celery import shared_task, current_app
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from .models import Order, NotificationLog, NewsletterSubscriber, ContactMessage, Profile, UserProfile, LoginActivity
from services.sms_service import send_welcome_sms as _send_welcome_sms, send_login_notification_sms as _send_login_sms
from services.email_service import send_welcome_email as _send_welcome_email, send_login_notification_email as _send_login_email

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe Delay Utility
# ---------------------------------------------------------------------------

_broker_available = None

def check_broker_availability():
    """Check if the Celery message broker is reachable."""
    global _broker_available
    if _broker_available is not None:
        return _broker_available

    try:
        from celery.utils.collections import force_mapping
        conn = current_app.connection_for_read()
        conn.connect()
        conn.release()
        _broker_available = True
        logger.info("Celery broker is available at %s", current_app.conf.broker_url)
    except Exception as exc:
        _broker_available = False
        logger.warning("Celery broker is NOT available at %s: %s", getattr(current_app.conf, 'broker_url', 'unknown'), exc)
    return _broker_available


def reset_broker_cache():
    """Reset the broker availability cache."""
    global _broker_available
    _broker_available = None


def safe_delay(task, *args, **kwargs):
    """
    Safely dispatch a Celery task. If the broker is unreachable, executes the
    task synchronously so that the caller never sees a ConnectionRefusedError.
    """
    broker_url = getattr(settings, 'CELERY_BROKER_URL', 'memory://')
    local_transports = ('memory://', 'django://', 'sqla+sqlite://')
    use_local_transport = any(broker_url.startswith(t) for t in local_transports)

    if use_local_transport:
        try:
            async_result = task.delay(*args, **kwargs)
            logger.info("Task %s dispatched asynchronously via local transport (task_id=%s)", task.__name__, async_result.id)
            return {'status': 'dispatched', 'dispatched_as': 'async', 'task_id': async_result.id}
        except Exception as exc:
            logger.warning("Async dispatch of %s failed via local transport, falling back sync: %s", task.__name__, exc)
            return _execute_sync(task, *args, **kwargs)

    try:
        if not check_broker_availability():
            logger.warning("Broker unavailable, executing %s synchronously (fallback)", task.__name__)
            return _execute_sync(task, *args, **kwargs)

        async_result = task.delay(*args, **kwargs)
        logger.info("Task %s dispatched asynchronously (task_id=%s)", task.__name__, async_result.id)
        return {'status': 'dispatched', 'dispatched_as': 'async', 'task_id': async_result.id}

    except (ConnectionRefusedError, ConnectionError, OSError) as exc:
        logger.warning("Broker connection failed (%s), executing %s synchronously", exc, task.__name__)
        _broker_available = False
        return _execute_sync(task, *args, **kwargs)

    except Exception as exc:
        logger.warning("Unexpected error dispatching %s (%s), executing synchronously", task.__name__, exc, exc_info=True)
        return _execute_sync(task, *args, **kwargs)


def _execute_sync(task, *args, **kwargs):
    """Execute a Celery task synchronously as a fallback."""
    try:
        logger.info("Executing %s synchronously (fallback)", task.__name__)
        result = task(*args, **kwargs)
        logger.info("Sync fallback of %s completed: %s", task.__name__, result)
        result = result or {}
        if isinstance(result, dict):
            result['dispatched_as'] = 'sync_fallback'
        return result
    except Exception as exc:
        logger.error("Sync fallback of %s failed: %s", task.__name__, exc, exc_info=True)
        return {'status': 'failed', 'dispatched_as': 'sync_fallback', 'error': str(exc)}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_customer_info(order):
    """Extract customer name, email, phone from order and related models."""
    shipping_address = getattr(order, 'shipping_address', None)

    customer_name = order.user.get_full_name() or order.user.username
    if shipping_address and shipping_address.full_name:
        customer_name = shipping_address.full_name

    customer_email = order.user.email
    if not customer_email and shipping_address and shipping_address.email:
        customer_email = shipping_address.email

    customer_phone = ''
    if shipping_address and shipping_address.phone:
        customer_phone = shipping_address.phone
    else:
        user_profile = getattr(order.user, 'userprofile', None)
        if user_profile and user_profile.phone_number:
            customer_phone = user_profile.phone_number
        else:
            phone_profile = getattr(order.user, 'phone_profile', None)
            if phone_profile and phone_profile.phone_number:
                customer_phone = phone_profile.phone_number

    return customer_name, customer_email, customer_phone


def _get_or_create_notification_log(order):
    """Get existing NotificationLog for the order or create a new one."""
    log = NotificationLog.objects.filter(order=order).first()
    if not log:
        log = NotificationLog.objects.create(
            order=order,
            user=order.user,
            email_status='pending',
            sms_status='pending',
        )
    return log


def _verify_smtp_credentials():
    """Verify SMTP credentials are configured properly."""
    host = getattr(settings, 'EMAIL_HOST', None)
    port = getattr(settings, 'EMAIL_PORT', None)
    user = getattr(settings, 'EMAIL_HOST_USER', None)
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    if not all([host, port, user, password, from_email]):
        logger.error('SMTP not fully configured. host=%s, port=%s, user=%s, has_password=%s, from_email=%s', host, port, user, bool(password), from_email)
        return False
    return True


def _verify_twilio_credentials():
    """Verify Twilio credentials are configured properly."""
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
    from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)

    if not all([sid, token, from_number]):
        logger.error('Twilio not fully configured. has_sid=%s, has_token=%s, has_from_number=%s', bool(sid), bool(token), bool(from_number))
        return False
    return True


# ---------------------------------------------------------------------------
# Order notification tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_email(self, order_id):
    """Send order confirmation email via SMTP with Celery retry."""
    try:
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for email notification.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    customer_name, customer_email, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    if not customer_email:
        log.email_status = 'skipped'
        log.email_error_message = 'No valid email address'
        log.save()
        return {'status': 'skipped', 'reason': 'No email address'}

    if order.total_amount is None or order.total_amount <= 0:
        log.email_status = 'skipped'
        log.email_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'reason': 'Invalid total amount'}

    if not _verify_smtp_credentials():
        log.email_status = 'failed'
        log.email_error_message = 'SMTP credentials not configured'
        log.save()
        return {'status': 'failed', 'error': 'SMTP not configured'}

    order_items = list(order.items.select_related('product').all())
    shipping_address = getattr(order, 'shipping_address', None)

    subject = f"Order Confirmed Successfully - Order #{order.id}"
    html_message = render_to_string('emails/order_confirmation.html', {
        'order': order,
        'order_items': order_items,
        'shipping_address': shipping_address,
        'customer_name': customer_name,
        'customer_email': customer_email,
        'customer_phone': customer_phone,
    })
    plain_message = strip_tags(html_message)

    try:
        logger.info('Attempting to send confirmation email for order %s to %s', order_id, customer_email)
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        if sent_count == 1:
            log.email_status = 'sent'
            log.email_sent_at = timezone.now()
            log.email_error_message = ''
            log.save()
            logger.info('Email Sent Successfully | Order #%s | To: %s', order.id, customer_email)
            return {'status': 'success', 'channel': 'email', 'recipient': customer_email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        log.email_status = 'failed'
        log.email_error_message = error_msg
        log.save()

        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for email on order %s. Final error: %s', order_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_sms(self, order_id):
    """Send order confirmation SMS via Twilio with Celery retry."""
    try:
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for SMS notification.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    customer_name, customer_email, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    if not customer_phone:
        log.sms_status = 'skipped'
        log.sms_error_message = 'No valid phone number'
        log.save()
        return {'status': 'skipped', 'reason': 'No phone number'}

    if order.total_amount is None or order.total_amount <= 0:
        log.sms_status = 'skipped'
        log.sms_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'reason': 'Invalid total amount'}

    if not _verify_twilio_credentials():
        log.sms_status = 'failed'
        log.sms_error_message = 'Twilio credentials not configured'
        log.save()
        return {'status': 'failed', 'error': 'Twilio not configured'}

    message_text = (
        f"Hello {customer_name}, your order #{order.id} has been confirmed successfully. "
        f"Total Amount: ₹{order.total_amount}. Thank you for shopping with GrocHub."
    )

    try:
        client = Client(getattr(settings, 'TWILIO_ACCOUNT_SID', ''), getattr(settings, 'TWILIO_AUTH_TOKEN', ''))
        logger.info('Attempting to send confirmation SMS for order %s to %s', order_id, customer_phone)
        twilio_message = client.messages.create(
            body=message_text,
            from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
            to=customer_phone,
        )

        if twilio_message.sid:
            log.sms_status = 'sent'
            log.sms_sent_at = timezone.now()
            log.sms_error_message = ''
            log.save()
            logger.info('SMS Sent Successfully | Order #%s | To: %s | SID: %s', order.id, customer_phone, twilio_message.sid)
            return {'status': 'success', 'channel': 'sms', 'recipient': customer_phone, 'twilio_sid': twilio_message.sid}
        else:
            raise RuntimeError(f'Twilio did not return a message SID (status: {twilio_message.status})')

    except TwilioRestException as exc:
        error_msg = f'Twilio error {exc.code}: {exc.msg}'
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()

        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for SMS on order %s. Final error: %s', order_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}

    except Exception as exc:
        error_msg = str(exc)
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()

        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for SMS on order %s. Final error: %s', order_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_status_update_notifications(self, order_id, new_status):
    """
    Send email/SMS notification for a generic order status change.

    Uses the existing `emails/order_status_update.html` template so no second
    email system is introduced. In-app notifications are already created
    synchronously by the order service; this task only handles email/SMS.
    """
    try:
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for status notification.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    from .order_services import NOTIFICATION_MESSAGES
    status_label = dict(Order.ORDER_STATUS_CHOICES).get(new_status, new_status)
    customer_name, customer_email, customer_phone = _get_customer_info(order)

    log = _get_or_create_notification_log(order)

    # ── Email channel ──
    if customer_email and _verify_smtp_credentials():
        order_id_display = order.order_id or f"#{order.id}"
        message = NOTIFICATION_MESSAGES.get(new_status, f'Your order {order_id_display} status has been updated to {status_label}.').format(order_id=order_id_display)
        subject = f"GrocHub - Order {order_id_display} {status_label}"
        html_message = render_to_string('emails/order_status_update.html', {
            'order': order,
            'customer_name': customer_name,
            'old_status': '',  # rendered context fetched fresh below
            'new_status': status_label,
            'message': message,
            'track_url': f"/track-order/{order.id}/",
        })
        plain_message = strip_tags(html_message)
        try:
            sent_count = send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [customer_email],
                html_message=html_message,
                fail_silently=False,
            )
            if sent_count == 1:
                log.email_status = 'sent'
                log.email_sent_at = timezone.now()
                log.email_error_message = ''
                log.save()
            else:
                raise RuntimeError(f'SMTP returned sent_count={sent_count}')
        except Exception as exc:
            log.email_status = 'failed'
            log.email_error_message = str(exc)
            log.save()
            logger.warning('Status email failed for order %s: %s', order_id, exc)
    elif customer_email:
        log.email_status = 'skipped'
        log.email_error_message = 'SMTP not configured'
        log.save()

    # ── SMS channel ──
    if customer_phone and _verify_twilio_credentials():
        try:
            client = Client(getattr(settings, 'TWILIO_ACCOUNT_SID', ''), getattr(settings, 'TWILIO_AUTH_TOKEN', ''))
            message = NOTIFICATION_MESSAGES.get(new_status, f'Order {order.order_id or order.id} updated to {new_status}.').format(order_id=order.order_id or f"#{order.id}")
            twilio_message = client.messages.create(
                body=f"Hello {customer_name}, {message}",
                from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
                to=customer_phone,
            )
            if twilio_message.sid:
                log.sms_status = 'sent'
                log.sms_sent_at = timezone.now()
                log.sms_error_message = ''
                log.save()
        except Exception as exc:
            log.sms_status = 'failed'
            log.sms_error_message = str(exc)
            log.save()
            logger.exception('Status SMS failed for order %s: %s', order_id, exc)
    elif customer_phone:
        log.sms_status = 'skipped'
        log.sms_error_message = 'Twilio not configured'
        log.save()

    return {'status': 'processed', 'order_id': order_id, 'new_status': new_status}
def send_order_notifications(self, order_id):
    """Master task that dispatches both email and SMS tasks for an order."""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for notifications.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    if order.notification_sent:
        logger.info('Notifications already sent for order %s. Skipping.', order_id)
        return {'status': 'skipped', 'reason': 'Already sent'}

    logger.info('=== ORDER CONFIRMATION EVENT === Order #%s | User: %s ===', order.id, order.user.username)

    email_task = send_order_confirmation_email.delay(order_id)
    sms_task = send_order_confirmation_sms.delay(order_id)

    logger.info('Dispatched notification tasks for order %s: email_task=%s, sms_task=%s', order_id, email_task.id, sms_task.id)

    return {
        'status': 'dispatched',
        'email_task_id': email_task.id,
        'sms_task_id': sms_task.id,
    }


# ---------------------------------------------------------------------------
# Newsletter and contact tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_newsletter_notification_task(self, subscriber_email, subscribed_at_str):
    """Send newsletter subscription notification email to admin."""
    from services.email_service import send_newsletter_notification
    from datetime import datetime

    try:
        subscribed_at = datetime.fromisoformat(subscribed_at_str)
        logger.info('Dispatching newsletter notification for %s (async)', subscriber_email)
        result = send_newsletter_notification(subscriber_email, subscribed_at)
        logger.info('Newsletter notification task completed for %s: %s', subscriber_email, result)
        return result
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Newsletter notification task failed for %s: %s', subscriber_email, error_msg, exc_info=True)
        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for newsletter notification for %s. Final error: %s', subscriber_email, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_contact_notification_task(self, contact_message_id):
    """Send contact form notification email to admin."""
    from services.email_service import send_contact_notification

    try:
        contact_message = ContactMessage.objects.get(id=contact_message_id)
        logger.info('Dispatching contact notification for message #%s from %s (async)', contact_message_id, contact_message.email)
        result = send_contact_notification(contact_message)
        logger.info('Contact notification task completed for message #%s: %s', contact_message_id, result)
        return result
    except ContactMessage.DoesNotExist:
        logger.error('ContactMessage %s not found for notification.', contact_message_id)
        return {'status': 'error', 'error': 'ContactMessage not found'}
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Contact notification task failed for message #%s: %s', contact_message_id, error_msg, exc_info=True)
        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for contact notification for message #%s. Final error: %s', contact_message_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_contact_confirmation_task(self, contact_message_id):
    """Send contact form confirmation email to the user."""
    from services.email_service import send_contact_confirmation

    try:
        contact_message = ContactMessage.objects.get(id=contact_message_id)
        logger.info('Dispatching contact confirmation for message #%s to %s (async)', contact_message_id, contact_message.email)
        result = send_contact_confirmation(contact_message)
        logger.info('Contact confirmation task completed for message #%s: %s', contact_message_id, result)
        return result
    except ContactMessage.DoesNotExist:
        logger.error('ContactMessage %s not found for confirmation.', contact_message_id)
        return {'status': 'error', 'error': 'ContactMessage not found'}
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Contact confirmation task failed for message #%s: %s', contact_message_id, error_msg, exc_info=True)
        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for contact confirmation for message #%s. Final error: %s', contact_message_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


# ---------------------------------------------------------------------------
# Auth SMS tasks - welcome SMS and login notification SMS
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_welcome_sms_task(self, user_id):
    """Send welcome SMS after successful phone signup."""
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error('User %s not found for welcome SMS.', user_id)
        return {'status': 'error', 'error': 'User not found'}

    logger.info('=== WELCOME SMS EVENT === User %s | Phone profile exists: %s ===', user_id, bool(getattr(user, 'phone_profile', None)))

    try:
        result = _send_welcome_sms(user)
        logger.info('Welcome SMS task completed for user %s: %s', user_id, result)
        return result
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Welcome SMS task failed for user %s: %s', user_id, error_msg, exc_info=True)
        try:
            countdown = 120 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for welcome SMS for user %s. Final error: %s', user_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_login_sms_task(self, user_id, login_activity_id=None, request_data=None):
    """Send login notification SMS after successful login."""
    from django.contrib.auth.models import User
    from django.http import HttpRequest

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error('User %s not found for login SMS.', user_id)
        return {'status': 'error', 'error': 'User not found'}

    class _FakeRequest:
        def __init__(self, ua_string):
            self.META = {}
            if ua_string:
                self.META['HTTP_USER_AGENT'] = ua_string

    fake_request = _FakeRequest((request_data or {}).get('HTTP_USER_AGENT', ''))

    logger.info('=== LOGIN SMS EVENT === User %s | LoginActivity %s ===', user_id, login_activity_id)

    try:
        result = _send_login_sms(user, fake_request)
        logger.info('Login SMS task completed for user %s: %s', user_id, result)
        return result
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Login SMS task failed for user %s: %s', user_id, error_msg, exc_info=True)
        try:
            countdown = 120 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for login SMS for user %s. Final error: %s', user_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


# ---------------------------------------------------------------------------
# Login alert tasks - email and SMS
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_login_email_task(self, user_id, login_activity_id, request_data=None):
    """
    Send login alert email asynchronously.
    
    Args:
        user_id: ID of the User instance
        login_activity_id: ID of the LoginActivity instance
        request_data: Serialized request metadata (User-Agent, etc.)
    """
    from django.contrib.auth.models import User
    from django.http import HttpRequest

    try:
        user = User.objects.get(id=user_id)
        login_activity = LoginActivity.objects.get(id=login_activity_id)
    except (User.DoesNotExist, LoginActivity.DoesNotExist) as exc:
        logger.error('User %s or LoginActivity %s not found for login email.', user_id, login_activity_id)
        return {'status': 'error', 'error': 'User or LoginActivity not found'}

    class _FakeRequest:
        def __init__(self, ua_string):
            self.META = {}
            if ua_string:
                self.META['HTTP_USER_AGENT'] = ua_string

    fake_request = _FakeRequest((request_data or {}).get('HTTP_USER_AGENT', ''))

    logger.info('=== LOGIN EMAIL EVENT === User %s | LoginActivity %s ===', user_id, login_activity_id)

    try:
        result = _send_login_email(user, fake_request, login_activity)
        logger.info('Login email task completed for user %s: %s', user_id, result)
        return result
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Login email task failed for user %s: %s', user_id, error_msg, exc_info=True)
        try:
            countdown = 120 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for login email for user %s. Final error: %s', user_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_login_sms_task(self, user_id, login_activity_id, request_data=None):
    """
    Send login alert SMS asynchronously.
    
    Args:
        user_id: ID of the User instance
        login_activity_id: ID of the LoginActivity instance
        request_data: Serialized request metadata (User-Agent, etc.)
    """
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        login_activity = LoginActivity.objects.get(id=login_activity_id)
    except (User.DoesNotExist, LoginActivity.DoesNotExist) as exc:
        logger.error('User %s or LoginActivity %s not found for login SMS.', user_id, login_activity_id)
        return {'status': 'error', 'error': 'User or LoginActivity not found'}

    class _FakeRequest:
        def __init__(self, ua_string):
            self.META = {}
            if ua_string:
                self.META['HTTP_USER_AGENT'] = ua_string

    fake_request = _FakeRequest((request_data or {}).get('HTTP_USER_AGENT', ''))

    logger.info('=== LOGIN SMS EVENT === User %s | LoginActivity %s ===', user_id, login_activity_id)

    try:
        result = _send_login_sms(user, fake_request, login_activity)
        logger.info('Login SMS task completed for user %s: %s', user_id, result)
        return result
    except Exception as exc:
        error_msg = str(exc)
        logger.error('Login SMS task failed for user %s: %s', user_id, error_msg, exc_info=True)
        try:
            countdown = 120 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error('Max retries exceeded for login SMS for user %s. Final error: %s', user_id, error_msg)
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}