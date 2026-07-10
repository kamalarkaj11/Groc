from django.db import migrations
from django.utils import timezone
from decimal import Decimal


def seed_coupons(apps, schema_editor):
    Coupon = apps.get_model('store', 'Coupon')
    now = timezone.now()
    future = now + timezone.timedelta(days=365)

    coupons = [
        {
            'code': 'SAVE10',
            'discount_type': 'flat',
            'discount_value': Decimal('10.00'),
            'min_order_amount': Decimal('0.00'),
            'max_uses': None,
            'used_count': 0,
            'is_active': True,
            'valid_from': now,
            'valid_to': future,
            'description': 'Save ₹10 on your order!',
        },
        {
            'code': 'WELCOME20',
            'discount_type': 'flat',
            'discount_value': Decimal('20.00'),
            'min_order_amount': Decimal('100.00'),
            'max_uses': None,
            'used_count': 0,
            'is_active': True,
            'valid_from': now,
            'valid_to': future,
            'description': 'Welcome! Save ₹20 on orders above ₹100.',
        },
        {
            'code': 'FRESH50',
            'discount_type': 'flat',
            'discount_value': Decimal('50.00'),
            'min_order_amount': Decimal('300.00'),
            'max_uses': None,
            'used_count': 0,
            'is_active': True,
            'valid_from': now,
            'valid_to': future,
            'description': 'Fresh discount! Save ₹50 on orders above ₹300.',
        },
        {
            'code': 'GROCERY100',
            'discount_type': 'flat',
            'discount_value': Decimal('100.00'),
            'min_order_amount': Decimal('500.00'),
            'max_uses': 1000,
            'used_count': 0,
            'is_active': True,
            'valid_from': now,
            'valid_to': future,
            'description': 'Big savings! Save ₹100 on orders above ₹500. Limited uses!',
        },
    ]

    for data in coupons:
        Coupon.objects.get_or_create(code=data['code'], defaults=data)


def reverse_seed(apps, schema_editor):
    Coupon = apps.get_model('store', 'Coupon')
    Coupon.objects.filter(code__in=['SAVE10', 'WELCOME20', 'FRESH50', 'GROCERY100']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0039_coupon_order_coupon_code'),
    ]

    operations = [
        migrations.RunPython(seed_coupons, reverse_seed),
    ]
