"""
Centralized order status & lifecycle service.

This module is the single source of truth for order status transitions.
Every status change anywhere in the system (admin dashboard, Django admin,
Celery tasks, customer cancellation) must go through ``update_order_status``.

It validates transitions, records milestone timestamps, appends to the
immutable status-history log, keeps the tracking row in sync and triggers
customer notifications.
"""

import logging

from django.db import transaction
from django.utils import timezone

from .models import (
    Order,
    OrderStatusHistory,
    OrderTracking,
    OrderTrackingHistory,
    Notification,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status transition map
# ---------------------------------------------------------------------------
# Keyed by current status -> set of allowed next statuses.
# This is the authoritative guard for every status update.
ALLOWED_TRANSITIONS = {
    'pending': {
        'pending_payment', 'confirmed', 'processing', 'packed',
        'cancelled', 'payment_failed', 'delivery_failed',
    },
    'pending_payment': {
        'pending', 'confirmed', 'cancelled', 'payment_failed',
    },
    'confirmed': {
        'processing', 'packed', 'shipped', 'cancelled', 'delivery_failed',
    },
    'processing': {
        'packed', 'shipped', 'cancelled', 'delivery_failed',
    },
    'packed': {
        'shipped', 'out_for_delivery', 'delivered',
        'cancelled', 'delivery_failed',
    },
    'shipped': {
        'out_for_delivery', 'delivered', 'delivery_failed', 'returned',
    },
    'out_for_delivery': {
        'delivered', 'delivery_failed', 'returned',
    },
    'delivered': {
        'returned', 'refund_initiated',
    },
    'delivery_failed': {
        'out_for_delivery', 'delivered', 'cancelled', 'returned',
    },
    'payment_failed': {
        'pending', 'pending_payment', 'cancelled',
    },
    'cancelled': {
        'refund_initiated', 'refunded',
    },
    'returned': {
        'refund_initiated', 'refunded',
    },
    'refund_initiated': {
        'refunded',
    },
    'refunded': set(),
    'failed': {'cancelled', 'refund_initiated'},
}

# Terminal statuses (no further movement allowed).
TERMINAL_STATUSES = {'refunded', 'delivered'}

# Statuses in which a customer is allowed to cancel their own order.
CUSTOMER_CANCELLABLE_STATUSES = {
    'pending', 'pending_payment', 'confirmed', 'processing', 'payment_failed',
}

# Statuses for which a payment refund is applicable (must be paid first).
REFUNDABLE_PAYMENT_STATUSES = {'paid', 'refund_pending'}

# Statuses that must record milestone timestamps.
MILESTONE_TIMESTAMP_FIELDS = {
    'pending': 'ordered_at',
    'pending_payment': None,
    'payment_failed': None,
    'confirmed': 'confirmed_at',
    'processing': 'processing_at',
    'packed': 'packed_at',
    'shipped': 'shipped_at',
    'out_for_delivery': 'out_for_delivery_at',
    'delivered': 'delivered_at',
    'cancelled': 'cancelled_at',
    'refund_initiated': 'refund_initiated_at',
    'refunded': 'refunded_at',
    'delivery_failed': None,
    'returned': None,
    'failed': None,
}
# Default human-friendly messages shown to the customer in the timeline.
STATUS_MESSAGES = {
    'pending': 'Your order has been placed successfully.',
    'pending_payment': 'Your payment is pending. Please complete the payment to confirm your order.',
    'payment_failed': 'Your payment could not be processed. Please try again.',
    'confirmed': 'Your order has been confirmed and is being prepared.',
    'processing': 'Your order is being processed.',
    'packed': 'Your order has been packed and is ready for delivery.',
    'shipped': 'Your order has been shipped.',
    'out_for_delivery': 'Your order is out for delivery.',
    'delivered': 'Your order has been delivered successfully.',
    'cancelled': 'Your order has been cancelled.',
    'delivery_failed': 'Your delivery could not be completed. Our team will contact you.',
    'returned': 'Your order has been marked as returned.',
    'refund_initiated': 'Your refund has been initiated.',
    'refunded': 'Your refund has been processed successfully.',
    'failed': 'Your order could not be processed.',
}

# Notification messages (mirror the message but phrased for notification text).
NOTIFICATION_MESSAGES = {
    'confirmed': 'Your order {order_id} has been confirmed. We are preparing your items!',
    'processing': 'Your order {order_id} is now being processed.',
    'packed': 'Your order {order_id} has been packed and is ready for delivery.',
    'shipped': 'Your order {order_id} has been shipped!',
    'out_for_delivery': 'Your order {order_id} is out for delivery! Get ready to receive your groceries.',
    'delivered': 'Your order {order_id} has been delivered successfully. Enjoy your groceries!',
    'cancelled': 'Your order {order_id} has been cancelled.',
    'delivery_failed': 'We could not deliver order {order_id}. Our team will reach out to you shortly.',
    'returned': 'Your order {order_id} has been marked as returned.',
    'refund_initiated': 'A refund for order {order_id} has been initiated.',
    'refunded': 'Your refund for order {order_id} has been processed.',
    'pending_payment': 'Your order {order_id} is awaiting payment.',
    'payment_failed': 'Payment for order {order_id} failed. Please try again.',
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def is_valid_transition(current_status, new_status):
    """Return True if ``new_status`` is reachable from ``current_status``."""
    if current_status == new_status:
        return False
    return new_status in ALLOWED_TRANSITIONS.get(current_status, set())


def get_allowed_transitions(current_status):
    """Return the sorted list of statuses reachable from ``current_status``."""
    return sorted(ALLOWED_TRANSITIONS.get(current_status, set()))


def get_transition_message(current_status, new_status):
    """Return a human friendly message describing the status event."""
    return STATUS_MESSAGES.get(new_status, '')


def is_customer_cancellable(order):
    """Return True if the customer is allowed to cancel this order."""
    return order.status in CUSTOMER_CANCELLABLE_STATUSES
# ---------------------------------------------------------------------------
# Notification trigger
# ---------------------------------------------------------------------------

def _send_status_notifications(order, new_status):
    """Create in-app Notification and dispatch email/SMS tasks for a status change."""
    try:
        order_id = order.order_id or f"#{order.id}"
        template = NOTIFICATION_MESSAGES.get(new_status, '')
        if template:
            message = template.format(order_id=order_id)
            title = f"Order {dict(Order.ORDER_STATUS_CHOICES).get(new_status, new_status)}"
            Notification.objects.create(
                user=order.user,
                title=title,
                message=message,
                notification_type='order',
            )
    except Exception:
        logger.exception('Failed to create in-app notification for order %s', order.id)

    # Dispatch email/SMS asynchronously via Celery (safe_delay falls back to sync).
    try:
        from store.tasks import send_order_status_update_notifications, safe_delay
        safe_delay(send_order_status_update_notifications, order.id, new_status)
    except Exception:
        logger.exception('Failed to dispatch status notification task for order %s', order.id)


# ---------------------------------------------------------------------------
# Core status transition service
# ---------------------------------------------------------------------------

@transaction.atomic
def update_order_status(order, new_status, user=None, message=None, notes=None,
                        notify=True, allow_invalid=False, **extra):
    """
    Transition ``order`` to ``new_status`` atomically.

    Steps:
      1. Validate that the transition is allowed (unless ``allow_invalid``).
      2. Update the order status and record the correct milestone timestamp.
      3. Append an immutable OrderStatusHistory entry.
      4. Keep OrderTracking (visual progress) in sync + tracking history.
      5. Trigger customer notifications (in-app + email/SMS).

    Returns the updated ``order`` instance.

    Raises ``ValueError`` when the transition is invalid.
    """
    current = order.status
    new_status = str(new_status)

    if current == new_status:
        return order

    if not allow_invalid and not is_valid_transition(current, new_status):
        raise ValueError(
            f"Invalid status transition: '{current}' → '{new_status}'. "
            f"Allowed transitions from '{current}': {get_allowed_transitions(current)}"
        )

    changed_by_name = ''
    if user is not None and user.is_authenticated:
        changed_by_name = user.get_full_name() or user.username

    # Record milestone timestamp relevant to the new status (never overwrite).
    ts_field = MILESTONE_TIMESTAMP_FIELDS.get(new_status)
    if ts_field:
        if not getattr(order, ts_field):
            setattr(order, ts_field, timezone.now())

    order.status = new_status
# Keep tracking row in sync for the visual progress tracker.
    tracking, _ = OrderTracking.objects.get_or_create(order=order)
    if new_status in OrderTracking.TRACKING_STATUS_CHOICES_DICT:
        tracking.status = new_status
    if extra.get('tracking_number'):
        tracking.tracking_number = extra['tracking_number']
        order.tracking_number = extra['tracking_number']
    if extra.get('delivery_partner'):
        tracking.delivery_partner = extra['delivery_partner']
        order.delivery_partner = extra['delivery_partner']
    if extra.get('estimated_delivery_date'):
        tracking.estimated_delivery_date = extra['estimated_delivery_date']
    if extra.get('current_location'):
        tracking.current_location = extra['current_location']
    if extra.get('notes'):
        tracking.notes = extra['notes']
    tracking.save()

    # Immutable history record (never overwrites previous entries).
    default_message = get_transition_message(current, new_status)
    OrderStatusHistory.objects.create(
        order=order,
        previous_status=current,
        new_status=new_status,
        message=message or default_message,
        changed_by=user if (user is not None and user.is_authenticated) else None,
        changed_by_name=changed_by_name,
        notes=notes or f"{current} → {new_status}",
        refund_id=extra.get('refund_id', ''),
        refund_amount=extra.get('refund_amount'),
    )

    # Also append to OrderTrackingHistory for compatibility with the legacy
    # template loop that reads these rows for step timestamps.
    OrderTrackingHistory.objects.create(
        tracking=tracking,
        status=new_status,
        description=message or default_message,
    )

    order.save()

    if notify:
        _send_status_notifications(order, new_status)

    return order


# ---------------------------------------------------------------------------
# Cancellation + refund helpers
# ---------------------------------------------------------------------------

def cancel_order(order, user=None, reason='', message=None, notify=True):
    """
    Cancel an order when the business rules allow it.

    - If the order was already paid, payment is moved to 'refund_pending' so
      the refund workflow (initiated -> refunded) can run without claiming a
      completed refund that hasn't actually been processed by the gateway.
    """
    if order.status in ('cancelled', 'refund_initiated', 'refunded', 'delivered'):
        raise ValueError('This order cannot be cancelled in its current state.')

    if user is not None and user.is_authenticated and not user.is_staff:
        if not is_customer_cancellable(order):
            raise ValueError('This order can no longer be cancelled.')

    with transaction.atomic():
        order.cancel_reason = reason
        order = update_order_status(
            order, 'cancelled', user=user,
            message=message or 'Order cancelled by customer.',
            notes=f"Cancelled. Reason: {reason or 'not specified'}",
            notify=notify,
        )
        if order.payment_status in REFUNDABLE_PAYMENT_STATUSES:
            order.payment_status = 'refund_pending'
            order.save(update_fields=['payment_status'])
    return order


def initiate_refund(order, user=None, refund_id='', refund_amount=None, message=None, notify=True):
    """Move a cancelled/returned order into the refund workflow."""
    if order.status not in ('cancelled', 'returned'):
        raise ValueError('Refund can only be initiated for cancelled or returned orders.')
    return update_order_status(
        order, 'refund_initiated', user=user,
        message=message or 'Refund initiated.',
        notes='Refund initiated.',
        refund_id=refund_id,
        refund_amount=refund_amount,
        notify=notify,
    )


def mark_refunded(order, user=None, refund_id='', refund_amount=None):
    """Mark an order refunded after the payment gateway confirms the refund."""
    if order.status not in ('refund_initiated', 'cancelled', 'returned'):
        raise ValueError('Refund can only be completed for orders in refund workflow.')
    with transaction.atomic():
        order.payment_status = 'refunded'
        order = update_order_status(
            order, 'refunded', user=user,
            message='Refund processed successfully.',
            notes='Refund completed.',
            refund_id=refund_id,
            refund_amount=refund_amount or order.total_amount,
        )
        order.save(update_fields=['payment_status'])
    return order


# ---------------------------------------------------------------------------
# Order placement helper (used during checkout / webhook)
# ---------------------------------------------------------------------------

def record_order_placed(order, user=None, estimated_delivery_date=None):
    """Create the initial 'pending' status history + tracking row for a new order."""
    if not order.ordered_at:
        order.ordered_at = timezone.now()
    order.save(update_fields=['ordered_at'])

    tracking, created = OrderTracking.objects.get_or_create(order=order)
    if created or (tracking.status not in OrderTracking.TRACKING_STATUS_CHOICES_DICT):
        tracking.status = 'pending'
    if estimated_delivery_date:
        tracking.estimated_delivery_date = estimated_delivery_date
        order.expected_delivery_date = estimated_delivery_date
        order.save(update_fields=['expected_delivery_date'])
    tracking.save()

    if not OrderStatusHistory.objects.filter(order=order, new_status='pending').exists():
        OrderStatusHistory.objects.create(
            order=order,
            previous_status='',
            new_status='pending',
            message=STATUS_MESSAGES['pending'],
            changed_by=user if (user is not None and user.is_authenticated) else None,
            changed_by_name=(user.get_full_name() or user.username) if (user is not None and user.is_authenticated) else 'System',
            notes='Order placed.',
        )

    # Tracking history entry for the initial event.
    if not OrderTrackingHistory.objects.filter(tracking=tracking, status='pending').exists():
        OrderTrackingHistory.objects.create(
            tracking=tracking,
            status='pending',
            description=STATUS_MESSAGES['pending'],
        )
    return tracking