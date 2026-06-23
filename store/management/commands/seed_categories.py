"""
Management command to seed Grochub with default categories and subcategories.

Usage:
    python manage.py seed_categories
"""
from django.core.management.base import BaseCommand
from store.models import Category, Subcategory


CATEGORY_DATA = [
    {
        "name": "Fruits",
        "icon": "bi-apple",
        "description": "Fresh and dried fruits including apples, bananas, mangoes, oranges, grapes, and more.",
        "sort_order": 1,
        "subcategories": [
            {"name": "Fresh Fruits", "icon": "bi-apple", "sort_order": 1},
            {"name": "Exotic Fruits", "icon": "bi-globe", "sort_order": 2},
            {"name": "Seasonal Fruits", "icon": "bi-calendar-event", "sort_order": 3},
            {"name": "Dry Fruits", "icon": "bi-box", "sort_order": 4},
        ],
    },
    {
        "name": "Vegetables",
        "icon": "bi-tree",
        "description": "Fresh vegetables including leafy greens, root vegetables, and gourds.",
        "sort_order": 2,
        "subcategories": [
            {"name": "Leafy Vegetables", "icon": "bi-tree", "sort_order": 1},
            {"name": "Root Vegetables", "icon": "bi-flower1", "sort_order": 2},
            {"name": "Gourds", "icon": "bi-basket", "sort_order": 3},
            {"name": "Other Vegetables", "icon": "bi-box-seam", "sort_order": 4},
        ],
    },
    {
        "name": "Dairy",
        "icon": "bi-cup-hot",
        "description": "Milk, cheese, paneer, butter, yogurt, cream, ghee and other dairy products.",
        "sort_order": 3,
        "subcategories": [
            {"name": "Milk", "icon": "bi-cup-straw", "sort_order": 1},
            {"name": "Cheese", "icon": "bi-egg-fried", "sort_order": 2},
            {"name": "Butter", "icon": "bi-heart", "sort_order": 3},
            {"name": "Yogurt", "icon": "bi-droplet", "sort_order": 4},
            {"name": "Cream", "icon": "bi-droplet-fill", "sort_order": 5},
            {"name": "Ghee", "icon": "bi-cup", "sort_order": 6},
        ],
    },
    {
        "name": "Bakery",
        "icon": "bi-cake",
        "description": "Breads, cakes, cookies, muffins, pastries and other baked goods.",
        "sort_order": 4,
        "subcategories": [
            {"name": "Bread", "icon": "bi-basket", "sort_order": 1},
            {"name": "Cakes", "icon": "bi-cake", "sort_order": 2},
            {"name": "Cookies", "icon": "bi-circle", "sort_order": 3},
            {"name": "Snacks", "icon": "bi-bag", "sort_order": 4},
        ],
    },
    {
        "name": "Beverages",
        "icon": "bi-cup-straw",
        "description": "Soft drinks, juices, tea, coffee, energy drinks and water.",
        "sort_order": 5,
        "subcategories": [
            {"name": "Soft Drinks", "icon": "bi-droplet", "sort_order": 1},
            {"name": "Juices", "icon": "bi-cup", "sort_order": 2},
            {"name": "Tea", "icon": "bi-mug", "sort_order": 3},
            {"name": "Coffee", "icon": "bi-cup-hot", "sort_order": 4},
            {"name": "Energy Drinks", "icon": "bi-lightning", "sort_order": 5},
            {"name": "Water", "icon": "bi-droplet-half", "sort_order": 6},
        ],
    },
    {
        "name": "Snacks",
        "icon": "bi-bag",
        "description": "Chips, namkeen, biscuits, chocolates, instant noodles, and ready-to-eat snacks.",
        "sort_order": 6,
        "subcategories": [
            {"name": "Chips", "icon": "bi-square", "sort_order": 1},
            {"name": "Namkeen", "icon": "bi-star", "sort_order": 2},
            {"name": "Biscuits", "icon": "bi-circle", "sort_order": 3},
            {"name": "Chocolates", "icon": "bi-heart-fill", "sort_order": 4},
            {"name": "Instant Food", "icon": "bi-lightning", "sort_order": 5},
            {"name": "Frozen Snacks", "icon": "bi-snow", "sort_order": 6},
        ],
    },
    {
        "name": "Grocery & Staples",
        "icon": "bi-box-seam",
        "description": "Rice, flour, pulses, sugar, salt, oils, spices, and other kitchen staples.",
        "sort_order": 7,
        "subcategories": [
            {"name": "Rice", "icon": "bi-box", "sort_order": 1},
            {"name": "Flour", "icon": "bi-box2", "sort_order": 2},
            {"name": "Pulses", "icon": "bi-circle", "sort_order": 3},
            {"name": "Sugar", "icon": "bi-droplet-fill", "sort_order": 4},
            {"name": "Oils", "icon": "bi-droplet", "sort_order": 5},
            {"name": "Spices", "icon": "bi-flower1", "sort_order": 6},
            {"name": "Salt", "icon": "bi-droplet-half", "sort_order": 7},
            {"name": "Condiments", "icon": "bi-heart", "sort_order": 8},
            {"name": "Cereals", "icon": "bi-box-seam", "sort_order": 9},
        ],
    },
    {
        "name": "Personal Care",
        "icon": "bi-person-heart",
        "description": "Soap, shampoo, face wash, toothpaste, lotions, deodorants, and hygiene products.",
        "sort_order": 8,
        "subcategories": [
            {"name": "Soap", "icon": "bi-heart", "sort_order": 1},
            {"name": "Shampoo", "icon": "bi-droplet", "sort_order": 2},
            {"name": "Face Wash", "icon": "bi-emoji-smile", "sort_order": 3},
            {"name": "Toothpaste", "icon": "bi-emoji-smile-fill", "sort_order": 4},
            {"name": "Skin Care", "icon": "bi-hand-index", "sort_order": 5},
            {"name": "Hair Care", "icon": "bi-person", "sort_order": 6},
            {"name": "Deodorants", "icon": "bi-heart-fill", "sort_order": 7},
            {"name": "Feminine Hygiene", "icon": "bi-shield", "sort_order": 8},
        ],
    },
    {
        "name": "Household",
        "icon": "bi-house-door",
        "description": "Detergents, dish wash, floor cleaners, tissue paper, garbage bags, and home care products.",
        "sort_order": 9,
        "subcategories": [
            {"name": "Detergents", "icon": "bi-droplet-half", "sort_order": 1},
            {"name": "Cleaning Supplies", "icon": "bi-brush", "sort_order": 2},
            {"name": "Kitchen Essentials", "icon": "bi-kitchen", "sort_order": 3},
            {"name": "Home Care", "icon": "bi-house-heart", "sort_order": 4},
        ],
    },
    {
        "name": "Frozen Foods",
        "icon": "bi-snow",
        "description": "Ice cream, frozen vegetables, frozen snacks, and frozen meat products.",
        "sort_order": 10,
        "subcategories": [
            {"name": "Ice Cream", "icon": "bi-egg", "sort_order": 1},
            {"name": "Frozen Vegetables", "icon": "bi-tree", "sort_order": 2},
            {"name": "Frozen Snacks", "icon": "bi-lightning", "sort_order": 3},
            {"name": "Frozen Meat", "icon": "bi-archive", "sort_order": 4},
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
