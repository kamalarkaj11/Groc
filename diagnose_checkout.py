import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
django.setup()
from store.forms import CheckoutShippingForm

sample = {
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
}
form = CheckoutShippingForm(sample)
print('valid', form.is_valid())
print('errors', form.errors)
print('cleaned', getattr(form, 'cleaned_data', None))
