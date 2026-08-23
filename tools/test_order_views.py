"""
HTTP-level smoke test for order tracking views & APIs.

Run:  python manage.py shell -c "exec(open('tools/test_order_views.py', encoding='utf-8').read())"
"""
import traceback
from decimal import Decimal
from datetime import timedelta

import django

django.setup()

from django.test.utils import setup_test_environment

setup_test_environment()  # adds 'testserver' to ALLOWED_HOSTS for the test client

# Keep tests fast — no real SMTP/Twilio.
import store.tasks as _tasks


def _fast_delay(task, *args, **kwargs):
    return {'status': 'skipped-in-test'}


_tasks.safe_delay = _fast_delay

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from store.models import Category, Product, Order, OrderItem
from store.order_services import record_order_placed, update_order_status

PASS = []
FAIL = []


def check(label, condition, extra=''):
    if condition:
        PASS.append(label)
        print(f"  [PASS] {label}")
    else:
        FAIL.append(f"{label} {extra}")
        print(f"  [FAIL] {label} {extra}")


def run():
    suffix = str(int(timezone.now().timestamp()))[-6:]
    owner = User.objects.create_user(username=f'httpown_{suffix}', email=f'h1_{suffix}@e.com', password='Passw0rd!')
    stranger = User.objects.create_user(username=f'httpstr_{suffix}', email=f'h2_{suffix}@e.com', password='Passw0rd!')
    staff = User.objects.create_user(username=f'httpadm_{suffix}', email=f'h3_{suffix}@e.com', password='Passw0rd!', is_staff=True)

    category = Category.objects.first() or Category.objects.create(name=f'HTTPCat_{suffix}')
    product = Product.objects.create(title=f'HTTP Banana {suffix}', description='t', price=Decimal('50.00'), category=category)

    order = Order.objects.create(user=owner, subtotal=Decimal('100.00'), total_amount=Decimal('110.00'))
    OrderItem.objects.create(order=order, product=product, quantity=2, price=Decimal('50.00'), product_name=product.title)
    record_order_placed(order, estimated_delivery_date=timezone.now().date() + timedelta(days=3))

    c_owner = Client()
    c_owner.login(username=owner.username, password='Passw0rd!')
    c_stranger = Client()
    c_stranger.login(username=stranger.username, password='Passw0rd!')
    c_staff = Client()
    c_staff.login(username=staff.username, password='Passw0rd!')
    c_anon = Client()

    print('\n== Tracking page ==')
    r = c_owner.get(f'/track-order/{order.id}/')
    check('owner sees tracking page', r.status_code == 200, r.status_code)
    body = r.content.decode()
    check('page shows order id', (order.order_id or '') in body)
    check('cancel button shown for pending order', 'Cancel Order' in body)
    check('processing step present', 'Processing' in body)
    check('view invoice button present', 'View Invoice' in body)

    r = c_stranger.get(f'/track-order/{order.id}/')
    check("stranger redirected away from tracking", r.status_code == 302, r.status_code)
    r = c_anon.get(f'/track-order/{order.id}/')
    check('anonymous redirected to login', r.status_code == 302, r.status_code)

    print('\n== My orders & order detail ==')
    r = c_owner.get('/my-orders/')
    check('my orders renders', r.status_code == 200, r.status_code)
    check('order listed on my orders', (order.order_id or '').encode() in r.content)

    r = c_owner.get(f'/orders/{order.id}/')
    check('order detail renders', r.status_code == 200, r.status_code)

    print('\n== APIs ==')
    r = c_anon.get('/api/orders/')
    check('anon list -> 401', r.status_code == 401, r.status_code)
    r = c_owner.get('/api/orders/')
    data = r.json()
    check('owner list -> 200 with results', r.status_code == 200 and data.get('count', 0) >= 1, r.status_code)

    r = c_stranger.get(f'/api/orders/{order.id}/')
    check("stranger detail -> 404 (hidden)", r.status_code == 404, r.status_code)
    r = c_owner.get(f'/api/orders/{order.id}/')
    check('owner detail -> 200 + items', r.status_code == 200 and len(r.json().get('items', [])) >= 1)
    r = c_owner.get(f'/api/orders/{order.id}/tracking/')
    tdata = r.json()
    check('tracking api has timeline', r.status_code == 200 and len(tdata.get('timeline', [])) >= 7)
    check('tracking api can_cancel true', tdata.get('can_cancel') is True)
    r = c_owner.get(f'/api/orders/{order.id}/history/')
    check('history api returns events', r.status_code == 200 and len(r.json().get('history', [])) >= 1)

    print('\n== Cancellation flow over HTTP ==')
    r = c_owner.post(f'/orders/{order.id}/cancel/', {'cancel_reason': ''})
    order.refresh_from_db()
    check('empty reason keeps order alive', order.status != 'cancelled')

    r = c_owner.post(f'/orders/{order.id}/cancel/', {'cancel_reason': 'Change of mind'})
    order.refresh_from_db()
    check('cancel POST works', order.status == 'cancelled')
    check('reason persisted', order.cancel_reason == 'Change of mind')
    check('tracking page now hides cancel', b'Cancel Order' not in c_owner.get(f'/track-order/{order.id}/').content)

    print('\n== Admin APIs & pages ==')
    r = c_owner.post(f'/api/admin/orders/{order.id}/status/', data='{"status":"refunded"}', content_type='application/json')
    check('non-staff blocked from admin status API', r.status_code == 403, r.status_code)

    # Cancelled orders can only move to refund states; try invalid first.
    r = c_staff.post(f'/api/admin/orders/{order.id}/status/', data='{"status":"shipped"}', content_type='application/json')
    check('staff invalid transition rejected', r.status_code == 400, r.status_code)

    order2 = Order.objects.create(user=owner, subtotal=Decimal('10.00'), total_amount=Decimal('12.00'))
    record_order_placed(order2)
    r = c_staff.post(f'/api/admin/orders/{order2.id}/status/',
                     data='{"status":"confirmed","message":"Confirmed via API","tracking_number":"GROC-TRK-842931","delivery_partner":"GrocHub Delivery"}',
                     content_type='application/json')
    check('staff valid transition accepted', r.status_code == 200, getattr(r, 'status_code', None))
    order2.refresh_from_db()
    check('status applied', order2.status == 'confirmed')
    check('tracking number saved', order2.tracking_number == 'GROC-TRK-842931')

    r = c_staff.get(f'/admin/orders/{order2.id}/')
    check('admin detail page renders', r.status_code == 200, r.status_code)
    body = r.content.decode()
    check('admin page shows confirmation modal', 'statusConfirmModal' in body)
    check('admin page shows tracking card', 'Delivery Partner' in body)
    check('invalid options disabled in select', '(not allowed)' in body)

    r = c_staff.get('/admin/orders/')
    check('admin dashboard renders', r.status_code == 200, r.status_code)


try:
    run()
except Exception as exc:
    traceback.print_exc()
    FAIL.append(f'UNEXPECTED: {exc}')
finally:
    print(f"\n================ RESULT: {len(PASS)} passed, {len(FAIL)} failed ================")
    for f in FAIL:
        print(f'   FAILED: {f}')