import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
django.setup()
from django.test import Client
from django.contrib.auth.models import User
from store.models import Product, CartItem

client = Client()
username = 'diaguser'
password = 'test12345'
user, created = User.objects.get_or_create(username=username, defaults={'email': 'diag@example.com'})
if created:
    user.set_password(password)
    user.save()
else:
    user.set_password(password)
    user.save()
client.login(username=username, password=password)
product = Product.objects.first()
if not product:
    raise SystemExit('No product found in database to add to cart.')
CartItem.objects.filter(user=user).delete()
CartItem.objects.create(user=user, product=product, quantity=1)

response = client.post('/checkout/', {
    'full_name': 'John Doe',
    'email': 'john@example.com',
    'address_line1': 'House No. 21, Green Park',
    'address_line2': 'Sector 15',
    'city': 'Gurugram',
    'state': 'HR',
    'pincode': '122001',
    'country': 'India',
    'delivery_instructions': 'Leave at the door',
    'phone': '+919876543210',
    'latitude': '28.4595',
    'longitude': '77.0266',
}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
print('status', response.status_code)
print('content', response.content)
print('json', getattr(response, 'json', lambda: None)())
