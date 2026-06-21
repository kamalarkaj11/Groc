"""
Order notification service — sends email & SMS confirmations synchronously.

This module provides a simple entry point for triggering notifications
by calling the reusable services in the ``services`` package.

Usage:
    from store.notifications import send_order_notifications
    send_order_notifications(order_id)
"""

import logging

from django.db import transaction

from .models import Order

logger = logging.getLogger('store.notifications')


def send_order_notifications(order_id):
    """
    Trigger order confirmation notifications (email + SMS) synchronously.

    This function is safe to call multiple times — notifications are only
    dispatched once per order by checking the ``notification_sent`` flag.

    Uses the services/notification_service which internally calls:
      - services/email_service.send_order_confirmation_email()
      - services/sms_service.send_order_confirmation_sms()

    Args:
        order_id: The ID of the Order instance to send notifications for.

    Returns:
        dict with status info, or None if the order doesn't exist.
    """
    try:
        order = Order.objects.select_related(
            'user', 'shipping_address'
        ).get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found. Cannot send notifications.', order_id)
        return None

    if order.notification_sent:
        logger.info(
            'Notifications already sent for order %s. Skipping.', order_id,
        )
        return {'status': 'skipped', 'reason': 'already_sent'}

    if not order.user:
        logger.error('Order %s has no associated user. Cannot send notifications.', order_id)
        return {'status': 'error', 'reason': 'no_user'}

    if order.total_amount is None or order.total_amount <= 0:
        logger.error(
            'Order %s has invalid total_amount=%s. Notifications skipped.',
            order_id, order.total_amount,
        )
        return {'status': 'error', 'reason': 'invalid_amount'}

    logger.info(
        'Order #%s confirmed. Sending notifications...', order_id,
    )

    try:
        from services.notification_service import send_order_confirmation_notifications

        result = send_order_confirmation_notifications(order)

        logger.info(
            'Notifications processed for order %s. Email: %s, SMS: %s',
            order_id,
            result.get('email_result', {}).get('status', 'unknown'),
            result.get('sms_result', {}).get('status', 'unknown'),
        )

        return result

    except Exception as exc:
        logger.error(
            'Failed to send notifications for order %s: %s',
            order_id, exc, exc_info=True,
        )
        return {'status': 'error', 'reason': str(exc)}
