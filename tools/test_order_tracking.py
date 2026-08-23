"""
End-to-end smoke test for the Order Tracking System.

Run with:  python manage.py shell < tools/test_order_tracking.py

Validates:
  1. Order creation + initial status history + tracking row
  2. Full lifecycle transitions with milestone timestamps
  3. Invalid transition rejection
  4. Customer cancellation rules (allowed & blocked)
  5. Refund workflow (initiate -> complete)
  6. Ownership enforcement via API helpers
  7. Notifications created on status change
"""
import traceback
from decimal import Decimal
from datetime import timedelta

import django

django.setup()

from django.contrib.auth.models import User
from django.utils import timezone

from store.models import (
    Category, Product, Order, OrderItem, OrderStatusHistory,
    OrderTracking, OrderTrackingHistory, Notification,
)
from store.order_services import (
    update_order_status, cancel_order, initiate_refund, mark_refunded,
    record_order_placed, is_valid_transition, is_customer_cancellable,
)

PASS = []
FAIL = []

# Keep the smoke test fast: skip real SMTP/Twilio attempts (they execute
# synchronously under the memory:// Celery transport) but keep in-app
# notification creation so it can still be verified below.
import store.tasks as _tasks
from store.models import Notification as _Notification
from store.order_services import NOTIFICATION_MESSAGES as _NM


def _fast_delay(task, *args, **kwargs):
    return {'status': 'skipped-in-test'}


_tasks.safe_delay = _fast_delay


def check(label, condition, extra=''):
    if condition:
        PASS.append(label)
        print(f"  [PASS] {label}")
    else:
        FAIL.append(f"{label} {extra}")
        print(f"  [FAIL] {label} {extra}")


def run():
    suffix = str(int(timezone.now().timestamp()))[-6:]
    user = User.objects.create_user(username=f'tester_{suffix}', email=f'test_{suffix}@example.com', password='x')
    category = Category.objects.first() or Category.objects.create(name=f'TestCat_{suffix}')
    product = Product.objects.create(
        title=f'Test Apple {suffix}', description='test', price=Decimal('90.00'),
        discount_price=Decimal('80.00'), category=category,
    )

    print('\n== 1. Order creation ==')
    order = Order.objects.create(user=user, subtotal=Decimal('160.00'), total_amount=Decimal('170.00'))
    OrderItem.objects.create(order=order, product=product, quantity=2, price=Decimal('80.00'),
                             product_name=product.title, discount=Decimal('0.00'))
    record_order_placed(order, user=user, estimated_delivery_date=timezone.now().date() + timedelta(days=3))
    order.refresh_from_db()
    check('order_id generated in GROC format', (order.order_id or '').startswith('GROC'), order.order_id)
    check('ordered_at recorded', order.ordered_at is not None)
    check('status history has Order Placed', OrderStatusHistory.objects.filter(order=order, new_status='pending').exists())
    check('tracking row exists', OrderTracking.objects.filter(order=order).exists())
    check('tracking history entry created', OrderTrackingHistory.objects.filter(tracking__order=order, status='pending').exists())
    check('expected_delivery_date set', order.expected_delivery_date is not None)

    # Snapshot independence
    product.delete()
    item = order.items.first()
    check('item snapshot survives product deletion', item.display_name.startswith('Test Apple'))

    print('\n== 2. Lifecycle progression ==')
    for new_status, ts_field in [
        ('confirmed', 'confirmed_at'),
        ('processing', 'processing_at'),
        ('packed', 'packed_at'),
        ('shipped', 'shipped_at'),
        ('out_for_delivery', 'out_for_delivery_at'),
        ('delivered', 'delivered_at'),
    ]:
        update_order_status(order, new_status)
        order.refresh_from_db()
        check(f'transition to {new_status}', order.status == new_status)
        check(f'{ts_field} recorded', getattr(order, ts_field) is not None)

    check('history count == 7 events',
          OrderStatusHistory.objects.filter(order=order).count() == 7,
          f"count={OrderStatusHistory.objects.filter(order=order).count()}")

    print('\n== 3. Invalid transitions blocked ==')
    check('delivered -> processing invalid', not is_valid_transition('delivered', 'processing'))
    try:
        update_order_status(order, 'processing')
        check('service raises on delivered->processing', False)
    except ValueError:
        check('service raises on delivered->processing', True)
    order.refresh_from_db()
    check('order unchanged after invalid attempt', order.status == 'delivered')

    print('\n== 4. Cancellation rules ==')
    order2 = Order.objects.create(user=user, subtotal=Decimal('10.00'), total_amount=Decimal('20.00'))
    record_order_placed(order2)
    update_order_status(order2, 'confirmed')
    order2.payment_status = 'paid'
    order2.save(update_fields=['payment_status'])
    check('confirmed order cancellable', is_customer_cancellable(order2))
    cancel_order(order2, user=user, reason='Change of mind')
    order2.refresh_from_db()
    check('order cancelled', order2.status == 'cancelled')
    check('cancel_reason saved', order2.cancel_reason == 'Change of mind')
    check('cancelled_at recorded', order2.cancelled_at is not None)
    check('paid payment moved to refund_pending', order2.payment_status == 'refund_pending')

    print('\n== 5. Refund workflow ==')
    initiate_refund(order2)
    order2.refresh_from_db()
    check('refund initiated', order2.status == 'refund_initiated')
    mark_refunded(order2)
    order2.refresh_from_db()
    check('refunded completed', order2.status == 'refunded')
    check('payment marked refunded only after completion', order2.payment_status == 'refunded')

    print('\n== 6. Customer cancellation blocked after shipping ==')
    order3 = Order.objects.create(user=user, subtotal=Decimal('5.00'), total_amount=Decimal('15.00'))
    record_order_placed(order3)
    update_order_status(order3, 'confirmed')
    update_order_status(order3, 'packed')
    update_order_status(order3, 'shipped')
    check('shipped order NOT customer-cancellable', not is_customer_cancellable(order3))
    try:
        cancel_order(order3, user=user, reason='too late')
        check('customer cancel after shipping rejected', False)
    except ValueError:
        check('customer cancel after shipping rejected', True)

    print('\n== 7. Notifications ==')
    notes = Notification.objects.filter(user=user, notification_type='order').count()
    check('in-app notifications created for status changes', notes >= 4, f'count={notes}')

    print('\n== 8. Ownership helper ==')
    other_user = User.objects.create_user(username=f'other_{suffix}', email=f'o_{suffix}@example.com', password='x')
    from django.http import Http404
    from store.views import _get_order_for_user
    try:
        _get_order_for_user(other_user, order.id)
        check('other user cannot access order', False)
    except Http404:
        check('other user cannot access order', True)
    got = _get_order_for_user(user, order.id)
    check('owner can access own order', got is not None and got.id == order.id)


try:
    run()
except Exception as exc:
    traceback.print_exc()
    FAIL.append(f'UNEXPECTED: {exc}')
finally:
    print(f"\n================ RESULT: {len(PASS)} passed, {len(FAIL)} failed ================")
    for f in FAIL:
        print(f'   FAILED: {f}')