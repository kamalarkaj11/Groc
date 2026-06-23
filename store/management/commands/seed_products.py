"""
Management command to seed Grochub with sample products for every subcategory.

Usage:
    python manage.py seed_products
"""
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from store.models import Category, Subcategory, Product


PRODUCT_TEMPLATES = {
    "Fresh Fruits": [
        {"title": "Premium Apples (Shimla)", "price": 120, "weight": "1 kg"},
        {"title": "Bananas (Robusta)", "price": 45, "weight": "1 dozen"},
        {"title": "Sweet Oranges", "price": 90, "weight": "1 kg"},
        {"title": "Fresh Grapes (Green)", "price": 140, "weight": "500 g"},
    ],
    "Exotic Fruits": [
        {"title": "Avocado (Imported)", "price": 199, "weight": "2 pcs"},
        {"title": "Kiwi (Imported)", "price": 150, "weight": "3 pcs"},
        {"title": "Dragon Fruit", "price": 180, "weight": "1 pc"},
        {"title": "Blueberries", "price": 250, "weight": "125 g"},
    ],
    "Seasonal Fruits": [
        {"title": "Mango Alphonso", "price": 350, "weight": "1 kg"},
        {"title": "Watermelon", "price": 80, "weight": "1 pc"},
        {"title": "Papaya", "price": 60, "weight": "1 pc"},
        {"title": "Pomegranate", "price": 120, "weight": "1 kg"},
    ],
    "Dry Fruits": [
        {"title": "California Almonds (Badam)", "price": 450, "weight": "500 g"},
        {"title": "Cashew Nuts (Kaju)", "price": 550, "weight": "500 g"},
        {"title": "Pistachios (Pista)", "price": 650, "weight": "500 g"},
        {"title": "Walnuts (Akrot)", "price": 500, "weight": "500 g"},
    ],
    "Leafy Vegetables": [
        {"title": "Fresh Spinach (Palak)", "price": 30, "weight": "250 g"},
        {"title": "Fenugreek Leaves (Methi)", "price": 25, "weight": "250 g"},
        {"title": "Coriander Leaves (Dhaniya)", "price": 15, "weight": "100 g"},
        {"title": "Curry Leaves (Kadi Patta)", "price": 12, "weight": "50 g"},
    ],
    "Root Vegetables": [
        {"title": "Fresh Potatoes", "price": 35, "weight": "1 kg"},
        {"title": "Red Onions", "price": 45, "weight": "1 kg"},
        {"title": "Fresh Carrots", "price": 55, "weight": "500 g"},
        {"title": "Beetroot", "price": 40, "weight": "500 g"},
    ],
    "Gourds": [
        {"title": "Bottle Gourd (Lauki)", "price": 25, "weight": "1 pc"},
        {"title": "Bitter Gourd (Karela)", "price": 30, "weight": "250 g"},
        {"title": "Ridge Gourd (Turai)", "price": 25, "weight": "250 g"},
        {"title": "Cucumber (Kheera)", "price": 20, "weight": "1 pc"},
    ],
    "Other Vegetables": [
        {"title": "Fresh Tomatoes", "price": 40, "weight": "1 kg"},
        {"title": "Capsicum (Green)", "price": 70, "weight": "500 g"},
        {"title": "Cauliflower (Phool Gobhi)", "price": 45, "weight": "1 pc"},
        {"title": "Mushroom (Button)", "price": 80, "weight": "200 g"},
    ],
    "Milk": [
        {"title": "Amul Full Cream Milk", "price": 68, "weight": "1 L"},
        {"title": "Amul Taaza Milk", "price": 54, "weight": "1 L"},
        {"title": "Amul Gold Milk", "price": 72, "weight": "1 L"},
        {"title": "Nestle A+ Milk", "price": 75, "weight": "1 L"},
    ],
    "Cheese": [
        {"title": "Amul Cheese Slices", "price": 140, "weight": "200 g"},
        {"title": "Amul Mozzarella Cheese", "price": 180, "weight": "200 g"},
        {"title": "Britannia Cheese Block", "price": 160, "weight": "200 g"},
        {"title": "Amul Paneer", "price": 110, "weight": "200 g"},
    ],
    "Butter": [
        {"title": "Amul Butter", "price": 58, "weight": "100 g"},
        {"title": "Amul Garlic Butter", "price": 85, "weight": "100 g"},
        {"title": "Nutralite Butter", "price": 65, "weight": "100 g"},
        {"title": "Amul Cooking Butter", "price": 240, "weight": "500 g"},
    ],
    "Yogurt": [
        {"title": "Amul Fresh Curd (Dahi)", "price": 45, "weight": "400 g"},
        {"title": "Amul Masti Lassi", "price": 30, "weight": "200 ml"},
        {"title": "Greek Yogurt", "price": 90, "weight": "200 g"},
        {"title": "Chaach (Buttermilk)", "price": 25, "weight": "200 ml"},
    ],
    "Cream": [
        {"title": "Amul Fresh Cream", "price": 65, "weight": "100 ml"},
        {"title": "Amul Whipping Cream", "price": 120, "weight": "200 ml"},
        {"title": "Nestle Fresh Cream", "price": 70, "weight": "100 ml"},
    ],
    "Ghee": [
        {"title": "Amul Pure Ghee", "price": 340, "weight": "500 ml"},
        {"title": "Nestle Ghee", "price": 360, "weight": "500 ml"},
        {"title": "Mother Dairy Ghee", "price": 330, "weight": "500 ml"},
    ],
    "Bread": [
        {"title": "Britannia Brown Bread", "price": 40, "weight": "400 g"},
        {"title": "Britannia White Bread", "price": 35, "weight": "400 g"},
        {"title": "Multigrain Bread", "price": 55, "weight": "400 g"},
        {"title": "Garlic Bread Loaf", "price": 60, "weight": "250 g"},
    ],
    "Cakes": [
        {"title": "Britannia Pineapple Cake", "price": 30, "weight": "60 g"},
        {"title": "Britannia Chocolate Cake", "price": 35, "weight": "60 g"},
        {"title": "Blueberry Muffins", "price": 50, "weight": "2 pcs"},
        {"title": "Black Forest Pastry", "price": 65, "weight": "1 pc"},
    ],
    "Cookies": [
        {"title": "Parle-G Gold", "price": 35, "weight": "200 g"},
        {"title": "Britannia Good Day", "price": 30, "weight": "100 g"},
        {"title": "Oreo Original", "price": 40, "weight": "120 g"},
        {"title": "Hide & Seek", "price": 35, "weight": "100 g"},
    ],
    "Soft Drinks": [
        {"title": "Coca-Cola", "price": 40, "weight": "750 ml"},
        {"title": "Pepsi", "price": 40, "weight": "750 ml"},
        {"title": "Sprite", "price": 38, "weight": "750 ml"},
        {"title": "Fanta Orange", "price": 38, "weight": "750 ml"},
    ],
    "Juices": [
        {"title": "Real Fruit Juice (Mango)", "price": 110, "weight": "1 L"},
        {"title": "Tropicana Orange Juice", "price": 120, "weight": "1 L"},
        {"title": "Minute Maid Apple", "price": 105, "weight": "1 L"},
        {"title": "Real Mixed Fruit", "price": 115, "weight": "1 L"},
    ],
    "Tea": [
        {"title": "Tata Tea Premium", "price": 180, "weight": "250 g"},
        {"title": "Red Label Natural Care", "price": 195, "weight": "250 g"},
        {"title": "Taj Mahal Tea", "price": 210, "weight": "250 g"},
        {"title": "Green Tea (Lipton)", "price": 160, "weight": "25 bags"},
    ],
    "Coffee": [
        {"title": "Nescafe Classic", "price": 140, "weight": "50 g"},
        {"title": "Bru Instant Coffee", "price": 130, "weight": "50 g"},
        {"title": "Nescafe Gold", "price": 350, "weight": "50 g"},
        {"title": "Filter Coffee Powder", "price": 120, "weight": "200 g"},
    ],
    "Energy Drinks": [
        {"title": "Red Bull", "price": 125, "weight": "250 ml"},
        {"title": "Monster Energy", "price": 110, "weight": "350 ml"},
        {"title": "Sting Energy", "price": 25, "weight": "250 ml"},
        {"title": "Glucon-D", "price": 140, "weight": "1 kg"},
    ],
    "Chips": [
        {"title": "Lay's Classic Salted", "price": 20, "weight": "52 g"},
        {"title": "Lay's Cream & Onion", "price": 20, "weight": "52 g"},
        {"title": "Bingo Mad Angles", "price": 20, "weight": "60 g"},
        {"title": "Kurkure Masala Munch", "price": 15, "weight": "50 g"},
    ],
    "Biscuits": [
        {"title": "Marie Gold", "price": 35, "weight": "200 g"},
        {"title": "Jim Jam", "price": 30, "weight": "100 g"},
        {"title": "Bourbon", "price": 30, "weight": "100 g"},
        {"title": "Nice Time", "price": 25, "weight": "100 g"},
    ],
    "Namkeen": [
        {"title": "Haldiram's Bhujia", "price": 55, "weight": "200 g"},
        {"title": "Haldiram's Aloo Bhujia", "price": 60, "weight": "200 g"},
        {"title": "Bikaji Bikaneri Bhujia", "price": 50, "weight": "200 g"},
        {"title": "Chana Jor Garam", "price": 35, "weight": "150 g"},
    ],
    "Chocolates": [
        {"title": "Dairy Milk Silk", "price": 80, "weight": "60 g"},
        {"title": "KitKat", "price": 40, "weight": "37 g"},
        {"title": "Five Star", "price": 20, "weight": "21.5 g"},
        {"title": "Ferrero Rocher", "price": 350, "weight": "100 g"},
    ],
    "Instant Food": [
        {"title": "Maggi Noodles (Masala)", "price": 14, "weight": "70 g"},
        {"title": "Yippee Noodles", "price": 13, "weight": "70 g"},
        {"title": "Top Ramen Curry", "price": 15, "weight": "70 g"},
        {"title": "Instant Pasta", "price": 45, "weight": "150 g"},
    ],
    "Detergents": [
        {"title": "Tide Plus Detergent", "price": 160, "weight": "2 kg"},
        {"title": "Ariel Matic", "price": 195, "weight": "2 kg"},
        {"title": "Surf Excel Easy Wash", "price": 170, "weight": "2 kg"},
        {"title": "Rin Detergent Bar", "price": 20, "weight": "250 g"},
    ],
    "Cleaning Supplies": [
        {"title": "Lizol Floor Cleaner", "price": 185, "weight": "2 L"},
        {"title": "Colin Glass Cleaner", "price": 120, "weight": "500 ml"},
        {"title": "Harpic Bathroom Cleaner", "price": 175, "weight": "1 L"},
        {"title": "Vim Dishwash Bar", "price": 25, "weight": "200 g"},
    ],
    "Kitchen Essentials": [
        {"title": "Aluminium Foil", "price": 85, "weight": "72 m"},
        {"title": "Butter Paper", "price": 45, "weight": "10 sheets"},
        {"title": "Garbage Bags (50 pcs)", "price": 60, "weight": "50 pcs"},
        {"title": "Kitchen Sponge (Pack)", "price": 35, "weight": "5 pcs"},
    ],
    "Home Care": [
        {"title": "Room Freshener (Lemon)", "price": 120, "weight": "1 pc"},
        {"title": "All Out Mosquito Repellent", "price": 85, "weight": "1 pc"},
        {"title": "Good Knight Power Saver", "price": 95, "weight": "1 pc"},
        {"title": "Shoe Polish (Black)", "price": 25, "weight": "50 g"},
    ],
    "Skin Care": [
        {"title": "Nivea Soft Cream", "price": 85, "weight": "100 ml"},
        {"title": "Vaseline Petroleum Jelly", "price": 75, "weight": "100 ml"},
        {"title": "Pond's Light Moisturizer", "price": 120, "weight": "150 ml"},
        {"title": "Himalaya Face Wash", "price": 140, "weight": "100 ml"},
    ],
    "Hair Care": [
        {"title": "Head & Shoulders Shampoo", "price": 180, "weight": "180 ml"},
        {"title": "Dove Hair Conditioner", "price": 195, "weight": "180 ml"},
        {"title": "Parachute Coconut Oil", "price": 75, "weight": "100 ml"},
        {"title": "Hair Serum", "price": 250, "weight": "50 ml"},
    ],
    "Deodorants": [
        {"title": "Wild Stone Deodorant", "price": 150, "weight": "150 ml"},
        {"title": "Park Avenue Deodorant", "price": 160, "weight": "150 ml"},
        {"title": "Nivea Body Spray", "price": 140, "weight": "150 ml"},
        {"title": "Rexona Deodorant", "price": 155, "weight": "150 ml"},
    ],
    "Feminine Hygiene": [
        {"title": "Whisper Sanitary Pads", "price": 85, "weight": "10 pcs"},
        {"title": "Stayfree Secure", "price": 80, "weight": "10 pcs"},
        {"title": "Kotex Sanitary Napkins", "price": 75, "weight": "10 pcs"},
    ],
    "Ice Cream": [
        {"title": "Vanilla Ice Cream", "price": 120, "weight": "500 ml"},
        {"title": "Chocolate Ice Cream", "price": 130, "weight": "500 ml"},
        {"title": "Magnum Almond", "price": 85, "weight": "80 ml"},
        {"title": "Cornetto Cone", "price": 45, "weight": "1 pc"},
    ],
    "Frozen Vegetables": [
        {"title": "Frozen Green Peas", "price": 65, "weight": "500 g"},
        {"title": "Frozen Sweet Corn", "price": 70, "weight": "500 g"},
        {"title": "Frozen Mixed Vegetables", "price": 75, "weight": "500 g"},
        {"title": "Frozen Spinach", "price": 55, "weight": "500 g"},
    ],
    "Frozen Snacks": [
        {"title": "Frozen Vegetable Paratha", "price": 85, "weight": "5 pcs"},
        {"title": "Frozen Pizza (Margherita)", "price": 150, "weight": "200 g"},
        {"title": "Frozen Spring Rolls", "price": 95, "weight": "10 pcs"},
        {"title": "Frozen French Fries", "price": 110, "weight": "500 g"},
    ],
}


class Command(BaseCommand):
    help = "Seed Grochub with sample products for every subcategory."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding products..."))

        total_created = 0
        total_skipped = 0

        for subcategory in Subcategory.objects.select_related("category").filter(is_active=True):
            templates = PRODUCT_TEMPLATES.get(subcategory.name, [])
            if not templates:
                self.stdout.write(self.style.WARNING(
                    f"  No templates for '{subcategory.name}', skipping."
                ))
                continue

            for tmpl in templates:
                title = tmpl["title"]
                existing = Product.objects.filter(title=title, subcategory=subcategory).first()
                if existing:
                    total_skipped += 1
                    continue

                slug = slugify(title)
                counter = 1
                original_slug = slug
                while Product.objects.filter(slug=slug).exists():
                    slug = f"{original_slug}-{counter}"
                    counter += 1

                discount_price = None
                price = tmpl["price"]
                if hash(title) % 10 < 3:
                    discount_price = round(price * 0.85, 2)

                Product.objects.create(
                    title=title,
                    slug=slug,
                    description=f"Fresh and quality {title.lower()} from {subcategory.category.name}.",
                    price=price,
                    discount_price=discount_price,
                    category=subcategory.category,
                    subcategory=subcategory,
                    weight=tmpl.get("weight", ""),
                    origin="India",
                    highlights=["100% Fresh", "Quality Guaranteed", "Fast Delivery"],
                    nutrition_info={"calories": "85 kcal", "protein": "2.5g", "carbs": "18g", "fat": "0.3g"},
                    is_out_of_stock=False,
                )
                total_created += 1
                self.stdout.write(f"  Created: {title}")

        self.stdout.write(self.style.SUCCESS(
            f"Done! Created {total_created} products, skipped {total_skipped} existing."
        ))
