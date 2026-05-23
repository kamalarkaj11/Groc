from django.core.management.base import BaseCommand
from django.utils.text import slugify

from store.models import Category, Product, Subcategory


MIN_PRODUCTS_PER_CATEGORY = 4


CATEGORY_PRODUCTS = {
    "Fruits": [
        {"title": "Fresh Mango", "subcategory": "Mango", "price": 120, "weight": "1 kg"},
        {"title": "Green Grapes", "subcategory": "Apple", "price": 90, "weight": "500 g"},
        {"title": "Sweet Banana", "subcategory": "Banana", "price": 45, "weight": "1 dozen"},
        {"title": "Kashmir Apple", "subcategory": "Apple", "price": 160, "weight": "1 kg"},
    ],
    "Vegetables": [
        {"title": "Fresh Potato", "subcategory": "Potato", "price": 35, "weight": "1 kg"},
        {"title": "Fresh Carrot", "subcategory": "Tomato", "price": 55, "weight": "500 g"},
        {"title": "Red Onion", "subcategory": "Onion", "price": 45, "weight": "1 kg"},
        {"title": "Ripe Tomato", "subcategory": "Tomato", "price": 40, "weight": "1 kg"},
    ],
    "Grains": [
        {"title": "Basmati Rice", "subcategory": "Rice", "price": 170, "weight": "1 kg"},
        {"title": "Whole Wheat Atta", "subcategory": "Wheat", "price": 65, "weight": "1 kg"},
        {"title": "Rolled Oats", "subcategory": "Oats", "price": 140, "weight": "500 g"},
        {"title": "Brown Rice", "subcategory": "Rice", "price": 120, "weight": "1 kg"},
    ],
    "Dairy": [
        {"title": "Fresh Curd", "subcategory": "Yogurt", "price": 45, "weight": "400 g"},
        {"title": "Greek Yogurt", "subcategory": "Yogurt", "price": 90, "weight": "200 g"},
        {"title": "Paneer Cubes", "subcategory": "Cheese", "price": 110, "weight": "200 g"},
        {"title": "Toned Milk", "subcategory": "Milk", "price": 58, "weight": "1 L"},
    ],
}


class Command(BaseCommand):
    help = "Ensure every active category has at least four active products."

    def handle(self, *args, **options):
        total_created = 0
        total_skipped = 0

        for category in Category.objects.filter(is_active=True).order_by("sort_order", "name"):
            active_count = Product.objects.filter(category=category, is_out_of_stock=False).count()
            needed = max(0, MIN_PRODUCTS_PER_CATEGORY - active_count)

            if needed == 0:
                total_skipped += 1
                self.stdout.write(f"{category.name}: already has {active_count} products.")
                continue

            templates = CATEGORY_PRODUCTS.get(category.name)
            if not templates:
                self.stdout.write(self.style.WARNING(
                    f"{category.name}: needs {needed} products but no templates are configured."
                ))
                continue

            created_for_category = 0
            for template in templates:
                if created_for_category >= needed:
                    break

                title = template["title"]
                if Product.objects.filter(category=category, title=title).exists():
                    continue

                subcategory = None
                subcategory_name = template.get("subcategory")
                if subcategory_name:
                    subcategory = Subcategory.objects.filter(
                        category=category,
                        name=subcategory_name,
                        is_active=True,
                    ).first()

                slug = slugify(title)
                original_slug = slug
                counter = 1
                while Product.objects.filter(slug=slug).exists():
                    slug = f"{original_slug}-{counter}"
                    counter += 1

                Product.objects.create(
                    title=title,
                    slug=slug,
                    description=f"Fresh and quality {title.lower()} for everyday grocery needs.",
                    price=template["price"],
                    category=category,
                    subcategory=subcategory,
                    weight=template.get("weight", ""),
                    origin="India",
                    highlights=["Quality Guaranteed", "Fresh Stock", "Fast Delivery"],
                    nutrition_info={},
                    is_out_of_stock=False,
                )
                created_for_category += 1
                total_created += 1

            self.stdout.write(f"{category.name}: created {created_for_category} product(s).")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {total_created} product(s), skipped {total_skipped} category/categories."
        ))
