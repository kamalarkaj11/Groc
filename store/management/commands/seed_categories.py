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
            {"name": "Exotic Fruits", "icon": "bi-globe", "sort_order": 3},
            {"name": "Organic Vegetables", "icon": "bi-heart", "sort_order": 4},
            {"name": "Seasonal Fruits", "icon": "bi-sun", "sort_order": 5},
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
            {"name": "Namkeen", "icon": "bi-star", "sort_order": 3},
            {"name": "Chocolates", "icon": "bi-heart-fill", "sort_order": 4},
            {"name": "Instant Food", "icon": "bi-lightning", "sort_order": 5},
        ],
    },
    {
        "name": "Household",
        "icon": "bi-house-door",
        "description": "Cleaning supplies, detergents, kitchen and bathroom essentials.",
        "sort_order": 5,
        "subcategories": [
            {"name": "Cleaning Supplies", "icon": "bi-brush", "sort_order": 1},
            {"name": "Detergents", "icon": "bi-droplet-half", "sort_order": 2},
            {"name": "Kitchen Essentials", "icon": "bi-kitchen", "sort_order": 3},
            {"name": "Bathroom Products", "icon": "bi-droplet", "sort_order": 4},
        ],
    },
    {
        "name": "Personal Care",
        "icon": "bi-person-heart",
        "description": "Skin care, hair care, oral care and body wash products.",
        "sort_order": 6,
        "subcategories": [
            {"name": "Skin Care", "icon": "bi-hand-thumbs-up", "sort_order": 1},
            {"name": "Hair Care", "icon": "bi-scissors", "sort_order": 2},
            {"name": "Oral Care", "icon": "bi-emoji-smile", "sort_order": 3},
            {"name": "Body Wash", "icon": "bi-droplet", "sort_order": 4},
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
