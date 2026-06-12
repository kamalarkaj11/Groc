import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
django.setup()
from django.test import Client
from django.contrib.auth.models import User
from store.models import Product, CartItem

client = Client(enforce_csrf_checks=True)
user, created = User.objects.get_or_create(username='diagcsfr', defaults={'email':'diagcsfr@example.com'})
if created:
    user.set_password('test12345')
    user.save()
else:
    user.set_password('test12345')
    user.save()
assert client.login(username='diagcsfr', password='test12345')
product = Product.objects.first()
if not product:
    raise SystemExit('No product found')
CartItem.objects.filter(user=user).delete()
CartItem.objects.create(user=user, product=product, quantity=1)
res = client.get('/checkout/')
print('GET checkout', res.status_code)
print('cookies', client.cookies.items())

csrftoken = client.cookies['csrftoken'].value
print('csrf', csrftoken)

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
    'csrfmiddlewaretoken': csrftoken,
}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
print('POST status', response.status_code)
print('POST content', response.content)
try:
    print('json', response.json())
except Exception as exc:
    print('json error', exc)
