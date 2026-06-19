"""
Order notification service — sends email & SMS confirmations via Celery tasks.

This module provides a simple entry point for triggering notifications.
The actual sending logic with retries, logging, and database tracking
resides in store/tasks.py (Celery tasks).

Usage:
    from store.notifications import send_order_notifications
    send_order_notifications(order_id)
"""

import logging

from django.db import transaction

from .models import Order

logger = logging.getLogger(__name__)


def send_order_notifications(order_id):
    """
    Trigger order confirmation notifications (email + SMS) via Celery.

    This function is safe to call multiple times — notifications are only
    dispatched once per order by checking the ``notification_sent`` flag.

    The order confirmation process completes instantly without waiting for
    notification delivery (async via Celery).

    Args:
        order_id: The ID of the Order instance to send notifications for.

    Returns:
        dict with status info, or None if the order doesn't exist.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.error('Order %s not found. Cannot send notifications.', order_id)
        return None

    # Guard: only send once per order
    if order.notification_sent:
        logger.info(
            'Notifications already sent for order %s. Skipping.',
            order_id,
        )
        return {'status': 'skipped', 'reason': 'already_sent'}

    # Validate required data before dispatching
    if not order.user:
        logger.error('Order %s has no associated user. Cannot send notifications.', order_id)
        return {'status': 'error', 'reason': 'no_user'}

    if not order.user.email:
        logger.warning(
            'Order %s user %s has no email. SMS-only delivery will be attempted.',
            order_id, order.user.id,
        )

    if order.total_amount is None or order.total_amount <= 0:
        logger.error(
            'Order %s has invalid total_amount=%s. Notifications skipped.',
            order_id, order.total_amount,
        )
        return {'status': 'error', 'reason': 'invalid_amount'}

    # Dispatch Celery task
    try:
        # Import here to avoid circular imports at module level
        from .tasks import send_order_notifications as celery_send_notifications

        result = celery_send_notifications.delay(order_id)
        logger.info(
            'Dispatched Celery notification task for order %s: task_id=%s',
            order_id, result.id,
        )

        # Mark notification_sent to prevent duplicate dispatches
        # (The Celery tasks handle the email_sent/sms_sent flags individually)
        with transaction.atomic():
            order.notification_sent = True
            order.save(update_fields=['notification_sent'])

        return {
            'status': 'dispatched',
            'task_id': result.id,
        }

    except Exception as exc:
        logger.error(
            'Failed to dispatch Celery notification task for order %s: %s',
            order_id, exc,
            exc_info=True,
        )
        return {'status': 'error', 'reason': str(exc)}