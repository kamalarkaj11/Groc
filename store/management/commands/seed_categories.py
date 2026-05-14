"""
Management command to seed Grochub with default categories and subcategories.

Usage:
    python manage.py seed_categories
"""
from django.core.management.base import BaseCommand
from store.models import Category, Subcategory


CATEGORY_DATA = [
    {
        "name": "Fruits & Vegetables",
        "icon": "bi-basket2",
        "description": "Fresh fruits and vegetables delivered daily.",
        "sort_order": 1,
        "subcategories": [
            {"name": "Fresh Fruits", "icon": "bi-apple", "sort_order": 1},
            {"name": "Leafy Vegetables", "icon": "bi-tree", "sort_order": 2},
            {"name": "Organic Vegetables", "icon": "bi-heart", "sort_order": 3},
            {"name": "Exotic Fruits", "icon": "bi-globe", "sort_order": 4},
        ],
    },
    {
        "name": "Dairy & Bakery",
        "icon": "bi-cup-hot",
        "description": "Milk, cheese, butter, breads, cakes and cookies.",
        "sort_order": 2,
        "subcategories": [
            {"name": "Milk", "icon": "bi-cup-straw", "sort_order": 1},
            {"name": "Cheese", "icon": "bi-egg-fried", "sort_order": 2},
            {"name": "Butter", "icon": "bi-heart", "sort_order": 3},
            {"name": "Bread", "icon": "bi-basket", "sort_order": 4},
            {"name": "Cakes", "icon": "bi-cake", "sort_order": 5},
            {"name": "Cookies", "icon": "bi-circle", "sort_order": 6},
        ],
    },
    {
        "name": "Beverages",
        "icon": "bi-cup-straw",
        "description": "Soft drinks, juices, tea, coffee and energy drinks.",
        "sort_order": 3,
        "subcategories": [
            {"name": "Soft Drinks", "icon": "bi-droplet", "sort_order": 1},
            {"name": "Juices", "icon": "bi-cup", "sort_order": 2},
            {"name": "Tea", "icon": "bi-mug", "sort_order": 3},
            {"name": "Coffee", "icon": "bi-cup-hot", "sort_order": 4},
            {"name": "Energy Drinks", "icon": "bi-lightning", "sort_order": 5},
        ],
    },
    {
        "name": "Snacks",
        "icon": "bi-bag",
        "description": "Chips, biscuits, namkeen, chocolates and instant food.",
        "sort_order": 4,
        "subcategories": [
            {"name": "Chips", "icon": "bi-circle-square", "sort_order": 1},
            {"name": "Biscuits", "icon": "bi-circle", "sort_order": 2},
            {"name": "Chocolates", "icon": "bi-heart-fill", "sort_order": 3},
            {"name": "Namkeen", "icon": "bi-star", "sort_order": 4},
        ],
    },
    {
        "name": "Grocery & Staples",
        "icon": "bi-box-seam",
        "description": "Rice, flour, pulses, sugar, salt and spices.",
        "sort_order": 5,
        "subcategories": [
            {"name": "Rice", "icon": "bi-box", "sort_order": 1},
            {"name": "Flour", "icon": "bi-box2", "sort_order": 2},
            {"name": "Pulses", "icon": "bi-circle", "sort_order": 3},
            {"name": "Sugar", "icon": "bi-droplet-fill", "sort_order": 4},
            {"name": "Salt", "icon": "bi-droplet", "sort_order": 5},
            {"name": "Spices", "icon": "bi-flower1", "sort_order": 6},
        ],
    },
    {
        "name": "Personal Care",
        "icon": "bi-person-heart",
        "description": "Shampoo, soap, face wash, toothpaste and more.",
        "sort_order": 6,
        "subcategories": [
            {"name": "Shampoo", "icon": "bi-droplet", "sort_order": 1},
            {"name": "Soap", "icon": "bi-heart", "sort_order": 2},
            {"name": "Face Wash", "icon": "bi-emoji-smile", "sort_order": 3},
            {"name": "Toothpaste", "icon": "bi-emoji-smile-fill", "sort_order": 4},
        ],
    },
    {
        "name": "Household Items",
        "icon": "bi-house-door",
        "description": "Detergents, cleaning supplies, kitchen and bathroom essentials.",
        "sort_order": 7,
        "subcategories": [
            {"name": "Detergents", "icon": "bi-droplet-half", "sort_order": 1},
            {"name": "Cleaning Supplies", "icon": "bi-brush", "sort_order": 2},
            {"name": "Kitchen Tools", "icon": "bi-kitchen", "sort_order": 3},
            {"name": "Bathroom Essentials", "icon": "bi-droplet", "sort_order": 4},
        ],
    },
    {
        "name": "Frozen Foods",
        "icon": "bi-snow",
        "description": "Ice cream, frozen snacks and frozen vegetables.",
        "sort_order": 8,
        "subcategories": [
            {"name": "Ice Cream", "icon": "bi-egg", "sort_order": 1},
            {"name": "Frozen Snacks", "icon": "bi-lightning", "sort_order": 2},
            {"name": "Frozen Vegetables", "icon": "bi-tree", "sort_order": 3},
        ],
    },
    {
        "name": "Baby Care",
        "icon": "bi-emoji-heart-fill",
        "description": "Baby food, diapers and baby soap products.",
        "sort_order": 9,
        "subcategories": [
            {"name": "Baby Food", "icon": "bi-cup", "sort_order": 1},
            {"name": "Diapers", "icon": "bi-box-seam", "sort_order": 2},
            {"name": "Baby Soap", "icon": "bi-droplet", "sort_order": 3},
        ],
    },
    {
        "name": "Pet Care",
        "icon": "bi-paw",
        "description": "Dog food, cat food and pet accessories.",
        "sort_order": 10,
        "subcategories": [
            {"name": "Dog Food", "icon": "bi-paw-fill", "sort_order": 1},
            {"name": "Cat Food", "icon": "bi-paw", "sort_order": 2},
            {"name": "Pet Accessories", "icon": "bi-heart", "sort_order": 3},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed Grochub with default categories and subcategories."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding categories and subcategories..."))

        total_cats = 0
        total_subs = 0

        for cat_data in CATEGORY_DATA:
            category, cat_created = Category.objects.get_or_create(
                name=cat_data["name"],
                defaults={
                    "icon": cat_data.get("icon", ""),
                    "description": cat_data.get("description", ""),
                    "sort_order": cat_data.get("sort_order", 0),
                    "is_active": True,
                },
            )
            if cat_created:
                total_cats += 1
                self.stdout.write(f"  Created category: {category.name}")
            else:
                self.stdout.write(f"  Found existing category: {category.name}")

            for sub_data in cat_data.get("subcategories", []):
                sub, sub_created = Subcategory.objects.get_or_create(
                    name=sub_data["name"],
                    category=category,
                    defaults={
                        "icon": sub_data.get("icon", ""),
                        "description": sub_data.get("description", ""),
                        "sort_order": sub_data.get("sort_order", 0),
                        "is_active": True,
                    },
                )
                if sub_created:
                    total_subs += 1
                    self.stdout.write(f"    Created subcategory: {sub.name}")
                else:
                    self.stdout.write(f"    Found existing subcategory: {sub.name}")

        self.stdout.write(self.style.SUCCESS(
            f"Done! Created {total_cats} categories and {total_subs} subcategories."
        ))
