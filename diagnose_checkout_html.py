import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
django.setup()
from django.test import Client
from django.contrib.auth.models import User
from store.models import Product, CartItem

client = Client()
user, created = User.objects.get_or_create(username='diagcheck2', defaults={'email': 'diagcheck2@example.com'})
if created:
    user.set_password('test12345')
    user.save()
else:
    user.set_password('test12345')
    user.save()
client.login(username='diagcheck2', password='test12345')
product = Product.objects.first()
if not product:
    raise SystemExit('No product found')
CartItem.objects.filter(user=user).delete()
CartItem.objects.create(user=user, product=product, quantity=1)
res = client.get('/checkout/')
html = res.content.decode('utf-8', errors='ignore')
print('status', res.status_code)
print('action=/checkout/ present', 'action="/checkout/"' in html)
print('csrf token present', 'csrfmiddlewaretoken' in html)
print('full_name present', 'name="full_name"' in html)
print('email present', 'name="email"' in html)
print('country present', 'name="country"' in html)
print('delivery_instructions present', 'name="delivery_instructions"' in html)
print('pay-button present', 'id="pay-button"' in html)
start = html.find('action="/checkout/"')
if start != -1:
    form_start = html.rfind('<form', 0, start)
    form_end = html.find('</form>', start)
    if form_start != -1 and form_end != -1:
        print(html[form_start:form_end+7])
    else:
        print('checkout form not found cleanly')
else:
    print('checkout action not found')
