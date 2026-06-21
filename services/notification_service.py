import logging

from django.db import transaction
from django.utils import timezone

from store.models import Order

logger = logging.getLogger(__name__)


def send_order_confirmation_notifications(order):
    """
    Send order confirmation notifications (email + SMS) for a confirmed order.

    Responsibilities:
      - Call email service to send confirmation email
      - Call SMS service to send confirmation SMS
      - Prevent duplicate notifications using Order notification_sent flag
      - Update Order model with delivery status fields
      - Do NOT break the order confirmation flow if one channel fails

    Args:
        order: Order instance (must be in 'confirmed' status)

    Returns:
        dict with keys:
            - email_result: result from email service
            - sms_result: result from SMS service
            - notification_sent: bool (True if at least one channel attempted)
    """
    if order.notification_sent:
        logger.info(
            'Notifications already sent for order %s. Skipping duplicate.',
            order.id,
        )
        return {
            'email_result': {'status': 'skipped', 'reason': 'already_sent'},
            'sms_result': {'status': 'skipped', 'reason': 'already_sent'},
            'notification_sent': True,
        }

    from .email_service import send_order_confirmation_email
    from .sms_service import send_order_confirmation_sms

    logger.info(
        '=== SENDING NOTIFICATIONS FOR ORDER #%s ===',
        order.id,
    )

    email_result = {'status': 'not_attempted'}
    sms_result = {'status': 'not_attempted'}

    try:
        email_result = send_order_confirmation_email(order)
    except Exception as exc:
        logger.error(
            'Email service raised unhandled exception for order %s: %s',
            order.id, exc, exc_info=True,
        )
        email_result = {'status': 'failed', 'channel': 'email', 'error': str(exc)}

    try:
        sms_result = send_order_confirmation_sms(order)
    except Exception as exc:
        logger.error(
            'SMS service raised unhandled exception for order %s: %s',
            order.id, exc, exc_info=True,
        )
        sms_result = {'status': 'failed', 'channel': 'sms', 'error': str(exc)}

    with transaction.atomic():
        order.email_sent = (email_result.get('status') == 'success')
        order.sms_sent = (sms_result.get('status') == 'success')
        order.notification_sent = True
        order.notification_sent_at = timezone.now()
        order.save(update_fields=['email_sent', 'sms_sent', 'notification_sent', 'notification_sent_at'])

    logger.info(
        '=== NOTIFICATIONS COMPLETE FOR ORDER #%s === Email: %s | SMS: %s',
        order.id,
        email_result.get('status', 'unknown'),
        sms_result.get('status', 'unknown'),
    )

    return {
        'email_result': email_result,
        'sms_result': sms_result,
        'notification_sent': True,
    }
