"""
Celery tasks for sending order confirmation notifications (email & SMS) and newsletter notifications.
Includes automatic retry with exponential backoff (up to 3 retries).
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from .models import Order, NotificationLog, NewsletterSubscriber

logger = logging.getLogger(__name__)


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
    """Verify SMTP credentials are configured properly before attempting to send."""
    host = getattr(settings, 'EMAIL_HOST', None)
    port = getattr(settings, 'EMAIL_PORT', None)
    user = getattr(settings, 'EMAIL_HOST_USER', None)
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', None)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    if not all([host, port, user, password, from_email]):
        logger.error(
            'SMTP not fully configured. host=%s, port=%s, user=%s, has_password=%s, from_email=%s',
            host, port, user, bool(password), from_email,
        )
        return False

    logger.info(
        'SMTP configuration verified: host=%s, port=%s, user=%s, from_email=%s',
        host, port, user, from_email,
    )
    return True


def _verify_twilio_credentials():
    """Verify Twilio credentials are configured properly."""
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
    from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)

    if not all([sid, token, from_number]):
        logger.error(
            'Twilio not fully configured. has_sid=%s, has_token=%s, has_from_number=%s',
            bool(sid), bool(token), bool(from_number),
        )
        return False

    logger.info(
        'Twilio configuration verified: SID=%s..., from=%s',
        sid[:10] if sid else 'N/A', from_number,
    )
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_email(self, order_id):
    """
    Send order confirmation email via SMTP with Celery retry.
    Retries: up to 3 times with exponential backoff (60s, 120s, 240s).
    """
    try:
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for email notification.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    customer_name, customer_email, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    # ---- Validation Checks ----
    if not customer_email:
        logger.warning('No valid email for order %s (user %s). Skipping email.', order_id, order.user.id)
        log.email_status = 'skipped'
        log.email_error_message = 'No valid email address'
        log.save()
        return {'status': 'skipped', 'reason': 'No email address'}

    if order.total_amount <= 0:
        logger.warning('Order %s total amount is %s. Skipping notifications.', order_id, order.total_amount)
        log.email_status = 'skipped'
        log.email_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'reason': 'Invalid total amount'}

    # ---- SMTP Verification ----
    if not _verify_smtp_credentials():
        log.email_status = 'failed'
        log.email_error_message = 'SMTP credentials not configured'
        log.save()
        return {'status': 'failed', 'error': 'SMTP not configured'}

    # ---- Gather order items ----
    order_items = list(order.items.select_related('product').all())
    shipping_address = getattr(order, 'shipping_address', None)

    # ---- Build Email ----
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

    # ---- Send Email ----
    try:
        logger.info(
            'Attempting to send confirmation email for order %s to %s (SMTP: %s:%s)',
            order_id, customer_email,
            getattr(settings, 'EMAIL_HOST', 'unknown'),
            getattr(settings, 'EMAIL_PORT', 'unknown'),
        )
        sent_count = send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(
            'SMTP response for order %s: sent_count=%s',
            order_id, sent_count,
        )
        if sent_count == 1:
            log.email_status = 'sent'
            log.email_sent_at = timezone.now()
            log.email_error_message = ''
            log.save()
            logger.info(
                '✓ Email delivery SUCCESS for order %s to %s',
                order_id, customer_email,
            )
            return {'status': 'success', 'channel': 'email', 'recipient': customer_email}
        else:
            raise RuntimeError(f'SMTP returned sent_count={sent_count}')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            '✗ Email delivery FAILED for order %s to %s: %s',
            order_id, customer_email, error_msg,
            exc_info=True,
        )
        log.email_status = 'failed'
        log.email_error_message = error_msg
        log.save()

        # Retry with exponential backoff
        try:
            countdown = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error(
                'Max retries exceeded for email on order %s. Final error: %s',
                order_id, error_msg,
            )
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_sms(self, order_id):
    """
    Send order confirmation SMS via Twilio with Celery retry.
    Retries: up to 3 times with exponential backoff (60s, 120s, 240s).
    """
    try:
        order = Order.objects.select_related('user', 'shipping_address').get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for SMS notification.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    customer_name, customer_email, customer_phone = _get_customer_info(order)
    log = _get_or_create_notification_log(order)

    # ---- Validation Checks ----
    if not customer_phone:
        logger.warning('No valid phone for order %s (user %s). Skipping SMS.', order_id, order.user.id)
        log.sms_status = 'skipped'
        log.sms_error_message = 'No valid phone number'
        log.save()
        return {'status': 'skipped', 'reason': 'No phone number'}

    if order.total_amount <= 0:
        logger.warning('Order %s total amount is %s. Skipping SMS.', order_id, order.total_amount)
        log.sms_status = 'skipped'
        log.sms_error_message = f'Invalid total amount: {order.total_amount}'
        log.save()
        return {'status': 'skipped', 'reason': 'Invalid total amount'}

    # ---- Twilio Verification ----
    if not _verify_twilio_credentials():
        log.sms_status = 'failed'
        log.sms_error_message = 'Twilio credentials not configured'
        log.save()
        return {'status': 'failed', 'error': 'Twilio not configured'}

    # ---- Build SMS ----
    message_text = (
        f"Hello {customer_name}, your order #{order.id} has been confirmed successfully. "
        f"Total Amount: ₹{order.total_amount}. "
        f"Thank you for shopping with GrocHub."
    )

    # ---- Send SMS via Twilio ----
    try:
        client = Client(
            getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
            getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        )
        logger.info(
            'Attempting to send confirmation SMS for order %s to %s',
            order_id, customer_phone,
        )
        twilio_message = client.messages.create(
            body=message_text,
            from_=getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
            to=customer_phone,
        )
        logger.info(
            '✓ Twilio API response for order %s: SID=%s, status=%s, error_code=%s, error_message=%s',
            order_id,
            twilio_message.sid,
            twilio_message.status,
            getattr(twilio_message, 'error_code', None),
            getattr(twilio_message, 'error_message', None),
        )

        # Check if Twilio accepted the message
        if twilio_message.sid:
            log.sms_status = 'sent'
            log.sms_sent_at = timezone.now()
            log.sms_error_message = ''
            log.save()
            logger.info(
                '✓ SMS delivery SUCCESS for order %s to %s (SID: %s)',
                order_id, customer_phone, twilio_message.sid,
            )
            return {
                'status': 'success',
                'channel': 'sms',
                'recipient': customer_phone,
                'twilio_sid': twilio_message.sid,
            }
        else:
            raise RuntimeError(f'Twilio did not return a message SID (status: {twilio_message.status})')

    except TwilioRestException as exc:
        error_msg = f'Twilio error {exc.code}: {exc.msg}'
        logger.error(
            '✗ Twilio API error for order %s to %s: %s',
            order_id, customer_phone, error_msg,
            exc_info=True,
        )
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()

        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error(
                'Max retries exceeded for SMS on order %s. Final error: %s',
                order_id, error_msg,
            )
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            '✗ SMS delivery FAILED for order %s to %s: %s',
            order_id, customer_phone, error_msg,
            exc_info=True,
        )
        log.sms_status = 'failed'
        log.sms_error_message = error_msg
        log.save()

        try:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error(
                'Max retries exceeded for SMS on order %s. Final error: %s',
                order_id, error_msg,
            )
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}


@shared_task(bind=True, max_retries=3)
def send_order_notifications(self, order_id):
    """
    Master task that dispatches both email and SMS tasks for an order.
    Ensures notifications are only sent once per order.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found for notifications.', order_id)
        return {'status': 'error', 'error': 'Order not found'}

    # Guard: only send once
    if order.notification_sent:
        logger.info('Notifications already sent for order %s. Skipping.', order_id)
        return {'status': 'skipped', 'reason': 'Already sent'}

    logger.info(
        '=== ORDER CONFIRMATION EVENT === Order #%s | User: %s (%s) | Email: %s | Phone: %s | Amount: ₹%s ===',
        order.id,
        order.user.get_full_name() or order.user.username,
        order.user.email,
        order.user.email or 'N/A',
        order.phone or 'N/A',
        order.total_amount,
    )

    # Dispatch email and SMS tasks in parallel
    email_task = send_order_confirmation_email.delay(order_id)
    sms_task = send_order_confirmation_sms.delay(order_id)

    logger.info(
        'Dispatched notification tasks for order %s: email_task=%s, sms_task=%s',
        order_id, email_task.id, sms_task.id,
    )

    return {
        'status': 'dispatched',
        'email_task_id': email_task.id,
        'sms_task_id': sms_task.id,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_newsletter_notification_task(self, subscriber_email, subscribed_at_str):
    """
    Celery task to send newsletter subscription notification email to admin.
    Runs asynchronously so the subscription endpoint returns immediately.

    Args:
        subscriber_email (str): The email address that subscribed.
        subscribed_at_str (str): ISO-formatted datetime string of subscription time.

    Retries: up to 3 times with exponential backoff (60s, 120s, 240s).
    """
    from services.email_service import send_newsletter_notification
    from datetime import datetime

    try:
        # Parse the datetime string back to a datetime object
        subscribed_at = datetime.fromisoformat(subscribed_at_str)

        logger.info(
            'Dispatching newsletter notification for %s (async)',
            subscriber_email,
        )
        result = send_newsletter_notification(subscriber_email, subscribed_at)
        logger.info(
            '✓ Newsletter notification task completed for %s: %s',
            subscriber_email, result,
        )
        return result
    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            '✗ Newsletter notification task failed for %s: %s',
            subscriber_email, error_msg,
            exc_info=True,
        )
        # Retry with exponential backoff
        try:
            countdown = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            logger.error(
                'Max retries exceeded for newsletter notification for %s. Final error: %s',
                subscriber_email, error_msg,
            )
            return {'status': 'failed', 'error': error_msg, 'retries_exhausted': True}