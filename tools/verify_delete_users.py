"""
Smoke test for the admin "delete selected users" permission fix.

Run with:  python tools/verify_delete_users.py

Validates that deleting a user who has Orders no longer gets blocked by the
read-only Order Status History / Order Tracking History models.

Background: Django's ``delete_selected`` action calls
``django.contrib.admin.utils.get_deleted_objects``. For every related object
that would be cascade-deleted, it invokes that model's registered ModelAdmin
``has_delete_permission`` and, if it returns False, adds the model's verbose
name to ``perms_needed``. Because ``OrderStatusHistoryAdmin`` and
``OrderTrackingHistoryAdmin`` hard-coded ``has_delete_permission -> False``,
any User deletion that cascaded through Order was blocked with
"Cannot delete users ... permission to delete ... Order Tracking History /
Order Status History".

The fix removed those overrides so the collector now resolves the *real*
per-user delete permission (letting a superuser / permitted staff delete
users whose orders cascade to these records).

Everything is created inside a transaction that is rolled back at the end so
the development database is left untouched.
"""
import os
import sys
import traceback
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')

# Make the project root importable (plain scripts don't get it on sys.path
# the way `manage.py` does).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

# Register models from store/admin.py (manage.py shell does this via
# autodiscovery; a plain script needs it done explicitly).
from django.contrib import admin

admin.autodiscover()

from django.contrib.admin.utils import get_deleted_objects
from django.contrib.auth.models import User

from store.models import (
    Category, Product, Order, OrderStatusHistory, OrderTracking,
    OrderTrackingHistory,
)

PASS = []
FAIL = []


def check(label, condition, extra=''):
    """Record a pass/fail for the given assertion."""
    if condition:
        PASS.append(label)
        print(f"  [PASS] {label}")
    else:
        FAIL.append(f"{label} {extra}")
        print(f"  [FAIL] {label} {extra}")


def main():
    # A superuser to act as the logged-in admin (mirrors `request.user`).
    superuser, _ = User.objects.get_or_create(
        username='__verify_superuser__',
        defaults=dict(is_superuser=True, is_staff=True),
    )
    request = SimpleNamespace(user=superuser)

    suffix = str(superuser.pk)
    customer = User.objects.create_user(
        username=f'del_user_{suffix}', email=f'del_{suffix}@example.com', password='x'
    )

    category = Category.objects.first() or Category.objects.create(name=f'DelCat_{suffix}')
    product = Product.objects.create(
        title=f'Del Apple {suffix}', description='test', price=Decimal('90.00'),
        discount_price=Decimal('80.00'), category=category,
    )
    order = Order.objects.create(
        user=customer, subtotal=Decimal('160.00'), total_amount=Decimal('170.00')
    )
    # Related records that get caught by the CASCADE collector:
    # Order -> OrderStatusHistory, Order -> OrderTracking -> OrderTrackingHistory
    OrderStatusHistory.objects.create(
        order=order, previous_status='', new_status='pending',
        changed_by_name='__verify_superuser__',
    )
    tracking = OrderTracking.objects.create(order=order, status='pending')
    OrderTrackingHistory.objects.create(tracking=tracking, status='pending')
    print(f'  Created customer user pk={customer.pk}, order pk={order.pk}')

    print()
    print('== Deleting the selected user (simulated admin confirmation) ==')
    deletable_objects, model_count, perms_needed, protected = get_deleted_objects(
        [customer], request, admin.site
    )
    print(f'   perms_needed = {sorted(perms_needed) if perms_needed else "{}"}')
    print(f'   protected    = {len(protected)}')
    print(f'   model_count  = {dict(model_count)}')

    check('no models flagged as lacking delete permission',
          not perms_needed, f'got {sorted(perms_needed)}')
    check('"Order Tracking History" not blocked',
          'Order Tracking History' not in perms_needed)
    check('"Order Status History" not blocked',
          'Order Status History' not in perms_needed)
    check('protected list is empty', not protected)
    check('OrderStatusHistory admin reports deletable',
          admin.site.get_model_admin(OrderStatusHistory).has_delete_permission(request))
    check('OrderTrackingHistory admin reports deletable',
          admin.site.get_model_admin(OrderTrackingHistory).has_delete_permission(request))


if __name__ == '__main__':
    try:
        from django.db import transaction

        with transaction.atomic():
            main()
            # Force a rollback so the dev database is not polluted.
            transaction.set_rollback(True)
    except Exception as exc:
        traceback.print_exc()
        FAIL.append(f'UNEXPECTED: {exc}')
    finally:
        print()
        print(f"================ RESULT: {len(PASS)} passed, {len(FAIL)} failed ================")
        for f in FAIL:
            print(f'   FAILED: {f}')
        sys.exit(1 if FAIL else 0)