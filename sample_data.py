import os
import django
from datetime import date, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')
django.setup()

from store.models import Category, Product, Review
from django.contrib.auth.models import User

print("Starting sample data creation...")

# Ensure sample categories (use existing if possible)
categories_needed = ['Fruits', 'Vegetables', 'Grains']
for cat_name in categories_needed:
    cat, created = Category.objects.get_or_create(name=cat_name, defaults={'slug': cat_name.lower()})
    if created:
        print(f"Created category: {cat_name}")
    else:
        print(f"Using existing category: {cat_name}")

# Get first 3 products and update with sample new fields
products = Product.objects.order_by('id')[:3]
if products.count() < 3:
    print("Warning: Less than 3 products found. Creating placeholders not implemented.")
else:
    sample_data = [
        {
            'weight': '1kg',
            'origin': 'Maharashtra, India',
            'highlights': ['100% Organic', 'Freshly Harvested', 'Premium Quality'],
            'nutrition_info': {'calories': 85, 'protein': 2.5, 'carbs': 18, 'fat': 0.5},
            'expiry_date': date.today() + timedelta(days=30),
        },
        {
            'weight': '500g',
            'origin': 'Karnataka, India',
            'highlights': ['Farm Fresh', 'No Pesticides', 'Rich in Vitamins'],
            'nutrition_info': {'calories': 52, 'protein': 1.1, 'carbs': 12, 'fat': 0.3},
            'expiry_date': date.today() + timedelta(days=45),
        },
        {
            'weight': '2kg',
            'origin': 'Punjab, India',
            'highlights': ['High Yield', 'Nutrient Dense', 'Locally Sourced'],
            'nutrition_info': {'calories': 350, 'protein': 12, 'carbs': 65, 'fat': 2.5},
            'expiry_date': date.today() + timedelta(days=60),
        }
    ]
    
    for i, prod in enumerate(products):
        data = sample_data[i]
        prod.weight = data['weight']
        prod.origin = data['origin']
        prod.highlights = data['highlights']
        prod.nutrition_info = data['nutrition_info']
        prod.expiry_date = data['expiry_date']
        prod.is_out_of_stock = False
        prod.save()
        print(f"Updated product: {prod.title}")

# Get users (assume at least 3)
users = User.objects.order_by('id')[:3]
if users.count() < 2:
    print("Warning: Need at least 2 users for reviews. Skipping reviews.")
else:
    # Sample reviews
    sample_reviews = [
        {'product_id': products[0].id if products else 1, 'user': users[0], 'rating': 5, 'comment': 'Excellent product! Fresh and tasty. Highly recommend for daily use.'},
        {'product_id': products[0].id if products else 1, 'user': users[1], 'rating': 4, 'comment': 'Good quality, arrived fresh. Nutrition info is helpful.'},
        {'product_id': products[1].id if products else 2, 'user': users[0], 'rating': 5, 'comment': 'Love the organic highlights. Perfect for health-conscious diet.'},
        {'product_id': products[1].id if products else 2, 'user': users[2], 'rating': 3, 'comment': 'Decent, but packaging could be better. Origin info trustworthy.'},
    ]
    
    created_reviews = 0
    for data in sample_reviews:
        review, created = Review.objects.get_or_create(
            product_id=data['product_id'],
            user=data['user'],
            defaults={'rating': data['rating'], 'comment': data['comment']}
        )
        if created:
            created_reviews += 1
    
    print(f"Created/updated {created_reviews} reviews.")

print("Sample data addition complete!")
print(f"Final counts - Products: {Product.objects.count()}, Reviews: {Review.objects.count()}")

