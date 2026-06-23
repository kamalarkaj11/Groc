"""
Management command to automatically classify all products into the most appropriate category.

Analyzes product title, description, brand hints, API payload, and other fields to
intelligently assign each product to the correct category. Supports dry-run mode,
automatic category creation, batched processing, and audit logging.

Usage:
    python manage.py auto_classify_products
    python manage.py auto_classify_products --dry-run
    python manage.py auto_classify_products --create-missing-categories
    python manage.py auto_classify_products --batch-size 200 --min-confidence 0.2
"""
import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from store.models import Category, Subcategory, Product

logger = logging.getLogger(__name__)


# ============================================================
# CATEGORY CLASSIFICATION RULES
# ============================================================
# Each category has:
#   - primary_keywords:  strong signals (title/description matches)
#   - secondary_keywords: weaker supporting signals
#   - brand_keywords:    brand names that strongly imply this category
#   - exclude_keywords:  if ANY match, the product is excluded from this category
#   - subcategory_rules: mapping of subcategory name -> list of keywords

CATEGORY_RULES = {
    "Fruits": {
        "description": "Fresh and dried fruits including apples, bananas, mangoes, oranges, grapes, watermelon, papaya, pomegranate, pineapple, kiwi, avocado, berries, dates, figs, and other fruit produce.",
        "icon": "bi-apple",
        "sort_order": 1,
        "primary_keywords": [
            "apple", "banana", "mango", "orange", "grapes", "watermelon",
            "papaya", "pomegranate", "pineapple", "kiwi", "avocado",
            "dragon fruit", "blueberry", "strawberry", "cherry",
            "fig", "dates", "olive", "apricot", "plum", "peach", "pear",
            "guava", "lychee", "jackfruit", "coconut", "tender coconut",
            "fruit", "fresh fruit", "seasonal fruit", "exotic fruit",
            "alphonso", "sweet lime", "mosambi", "sapota", "chikoo",
            "raspberry", "blackberry", "cranberry", "muskmelon",
            "honeydew", "cantaloupe", "fruit platter", "fruit basket",
            "dry fruit", "dried fruit", "raisin", "kishmish",
            "walnut", "akrot", "pistachio", "pista", "almond", "badam",
            "cashew", "kaju", "anjeer",
        ],
        "secondary_keywords": [
            "fresh", "ripe", "juicy", "sweet", "organic fruit",
            "fruit", "orchard", "harvest", "natural sugar",
        ],
        "brand_keywords": [],
        "exclude_keywords": [
            "vegetable", "potato", "onion", "tomato", "bhaji", "sabzi",
            "milk", "cheese", "bread", "soap", "detergent",
            "cooking oil", "coconut oil", "shampoo", "face wash",
        ],
        "subcategory_rules": {
            "Fresh Fruits": [
                "apple", "banana", "mango", "orange", "grapes",
                "watermelon", "papaya", "pomegranate", "pineapple",
                "guava", "lychee", "jackfruit", "sapota", "chikoo",
            ],
            "Exotic Fruits": [
                "kiwi", "avocado", "dragon fruit", "blueberry",
                "strawberry", "cherry", "fig", "olive", "apricot",
                "plum", "peach", "pear", "raspberry", "blackberry",
                "cranberry",
            ],
            "Seasonal Fruits": [
                "seasonal fruit", "alphonso", "muskmelon", "honeydew",
                "cantaloupe", "fruit platter", "fruit basket",
            ],
            "Dry Fruits": [
                "dry fruit", "dried fruit", "raisin", "kishmish",
                "walnut", "akrot", "pistachio", "pista", "almond",
                "badam", "cashew", "kaju", "anjeer", "dates",
            ],
        },
    },
    "Vegetables": {
        "description": "Fresh vegetables including leafy greens, root vegetables, gourds, and salad essentials.",
        "icon": "bi-tree",
        "sort_order": 2,
        "primary_keywords": [
            "spinach", "palak", "methi", "fenugreek", "coriander",
            "dhaniya", "curry leaves", "kadi patta", "lettuce",
            "onion", "potato", "tomato", "carrot", "capsicum",
            "cabbage", "cauliflower", "broccoli", "peas", "beans",
            "brinjal", "eggplant", "ladyfinger", "okra", "bhindi",
            "radish", "mooli", "beetroot", "beet", "ginger", "adrak",
            "garlic", "lassan", "chilli", "mirchi", "lemon", "nimbu",
            "lime", "cucumber", "kheera", "pumpkin", "kaddu",
            "bitter gourd", "karela", "ridge gourd", "turai",
            "bottle gourd", "lauki", "turnip", "shalgam",
            "sweet potato", "shakarkand", "yam", "suran", "taro",
            "arbi", "sprouts", "celery", "asparagus", "zucchini",
            "artichoke", "vegetable", "fresh vegetable", "sabzi",
            "green vegetable", "leafy vegetable", "organic vegetable",
            "mushroom", "button mushroom", "oyster mushroom",
            "spring onion", "green onion", "leek", "parsley",
            "mint", "pudina", "dill", "soya", "soybean",
        ],
        "secondary_keywords": [
            "fresh", "farm", "organic", "produce", "harvest",
            "tender", "crunchy", "vegetable", "veggie", "greens",
            "salad", "stir fry", "curry",
        ],
        "brand_keywords": [],
        "exclude_keywords": [
            "fruit", "mango", "apple", "banana", "ice cream",
            "soap", "shampoo", "detergent", "milk", "bread",
        ],
        "subcategory_rules": {
            "Leafy Vegetables": [
                "spinach", "palak", "methi", "fenugreek",
                "coriander", "dhaniya", "curry leaves", "kadi patta",
                "lettuce", "cabbage", "spring onion", "mint",
                "pudina", "parsley", "dill",
            ],
            "Root Vegetables": [
                "potato", "carrot", "radish", "mooli", "beetroot",
                "beet", "turnip", "shalgam", "sweet potato",
                "shakarkand", "yam", "suran", "taro", "arbi",
                "onion", "garlic", "lassan", "ginger", "adrak",
            ],
            "Gourds": [
                "pumpkin", "kaddu", "bitter gourd", "karela",
                "ridge gourd", "turai", "bottle gourd", "lauki",
                "cucumber", "kheera", "zucchini",
            ],
            "Other Vegetables": [
                "tomato", "capsicum", "cauliflower", "broccoli",
                "peas", "beans", "brinjal", "eggplant",
                "ladyfinger", "okra", "bhindi", "chilli", "mirchi",
                "lemon", "nimbu", "lime", "mushroom", "asparagus",
                "artichoke", "celery", "sprouts", "soya", "soybean",
            ],
        },
    },
    "Dairy": {
        "description": "Milk, cheese, paneer, butter, yogurt, cream, ghee, and other dairy products.",
        "icon": "bi-cup-hot",
        "sort_order": 3,
        "primary_keywords": [
            "milk", "amul milk", "full cream milk", "toned milk",
            "double toned milk", "cow milk", "buffalo milk",
            "cheese", "mozzarella", "cheddar", "processed cheese",
            "paneer", "cottage cheese", "tofu",
            "butter", "unsalted butter", "salted butter",
            "garlic butter", "cooking butter", "spread",
            "yogurt", "curd", "dahi", "greek yogurt",
            "lassi", "buttermilk", "chaach",
            "cream", "whipping cream", "fresh cream", "malai",
            "ghee", "clarified butter", "desi ghee",
            "condensed milk", "milk powder", "khoya", "mawa",
            "ice cream", "kulfi", "gelato", "frozen dessert",
            "paneer block", "yogurt drink",
        ],
        "secondary_keywords": [
            "dairy", "creamy", "rich", "pasteurized",
            "homogenized", "pure", "natural", "fresh",
        ],
        "brand_keywords": [
            "amul", "nestle", "mother dairy",
            "gokul", "vijaya", "heritage", "paras",
            "milkfood", "verka",
        ],
        "exclude_keywords": [
            "bread", "cake", "cookie", "soap", "shampoo",
            "vegetable", "fruit",
        ],
        "subcategory_rules": {
            "Milk": [
                "milk", "full cream milk", "toned milk",
                "double toned milk", "cow milk", "buffalo milk",
            ],
            "Cheese": [
                "cheese", "mozzarella", "cheddar", "processed cheese",
                "paneer", "cottage cheese", "paneer block", "tofu",
            ],
            "Butter": [
                "butter", "unsalted butter", "salted butter",
                "garlic butter", "cooking butter", "spread",
            ],
            "Yogurt": [
                "yogurt", "curd", "dahi", "greek yogurt",
                "lassi", "buttermilk", "chaach", "yogurt drink",
            ],
            "Cream": [
                "cream", "whipping cream", "fresh cream", "malai",
            ],
            "Ghee": [
                "ghee", "clarified butter", "desi ghee",
            ],
        },
    },
    "Bakery": {
        "description": "Breads, cakes, cookies, muffins, pastries, and other baked goods.",
        "icon": "bi-cake",
        "sort_order": 4,
        "primary_keywords": [
            "bread", "brown bread", "white bread", "multigrain bread",
            "sandwich bread", "whole wheat bread", "garlic bread",
            "fruit bread", "bread loaf", "burger bun", "pav",
            "bun", "croissant", "bagel", "baguette",
            "cake", "pastry", "muffin", "brownie", "cupcake",
            "chocolate cake", "vanilla cake", "pineapple cake",
            "black forest", "red velvet", "cheesecake",
            "cake", "pastry", "muffin", "brownie", "cupcake",
            "croissant", "donut", "doughnut",
            "waffle", "pancake", "crepe",
            "khari", "puff", "rusk", "toast", "cracker",
        ],
        "secondary_keywords": [
            "bakery", "baked", "freshly baked", "soft",
            "fluffy", "crispy", "buttery", "fresh",
        ],
        "brand_keywords": [
            "parle", "sunfeast", "cadbury",
            "modern", "english oven", "harvest gold",
        ],
        "exclude_keywords": [
            "milk", "cheese", "paneer", "soap", "shampoo",
            "detergent", "vegetable", "fruit",
        ],
        "subcategory_rules": {
            "Bread": [
                "bread", "brown bread", "white bread",
                "multigrain bread", "sandwich bread",
                "whole wheat bread", "garlic bread", "fruit bread",
                "bread loaf", "burger bun", "pav", "bun",
                "croissant", "bagel", "baguette",
            ],
            "Cakes": [
                "cake", "pastry", "muffin", "brownie", "cupcake",
                "chocolate cake", "vanilla cake", "pineapple cake",
                "black forest", "red velvet", "cheesecake",
                "donut", "doughnut", "waffle", "pancake",
            ],
            "Cookies": [
                "cookie", "brownie", "oreo",
            ],
            "Snacks": [
                "cracker", "rusk", "toast", "khari", "puff",
            ],
        },
    },
    "Beverages": {
        "description": "Soft drinks, juices, tea, coffee, energy drinks, and other beverages.",
        "icon": "bi-cup-straw",
        "sort_order": 5,
        "primary_keywords": [
            "coca-cola", "pepsi", "sprite", "fanta", "mountain dew",
            "7up", "mirinda", "thums up", "limca", "soda",
            "soft drink", "cola", "carbonated", "soda water",
            "fruit juice", "mixed fruit juice", "mango juice",
            "apple juice", "orange juice", "pomegranate juice",
            "real fruit juice", "tropicana", "minute maid",
            "juice", "fruit drink", "squash", "syrup",
            "concentrate", "cordial",
            "tea", "chai", "green tea", "black tea",
            "tata tea", "red label", "taj mahal", "lipton",
            "herbal tea", "detox tea", "lemon tea", "ice tea",
            "coffee", "nescafe", "bru", "filter coffee",
            "instant coffee", "cold coffee", "frappe",
            "espresso", "cappuccino", "latte",
            "energy drink", "red bull", "monster energy",
            "sting energy", "glucon-d", "sports drink",
            "electrolyte", "ORS", "gatorade",
            "protein shake", "protein drink",
            "coconut water", "tender coconut water",
            "smoothie", "milkshake", "shake",
            "bottled water", "mineral water", "spring water",
        ],
        "secondary_keywords": [
            "beverage", "drink", "refreshment", "thirst",
            "bottled", "can", "tetra pack", "chilled",
            "sparkling", "refreshing", "hydrating",
        ],
        "brand_keywords": [
            "coca-cola", "pepsi", "sprite", "fanta", "mountain dew",
            "7up", "mirinda", "thums up", "limca",
            "tropicana", "minute maid", "real",
            "bailley", "tata", "lipton", "nescafe",
            "bru", "red bull", "monster", "sting", "gatorade",
            "glucon-d", "paper boat", "dabur",
        ],
        "exclude_keywords": [
            "soap", "shampoo", "detergent", "bread", "vegetable",
        ],
        "subcategory_rules": {
            "Soft Drinks": [
                "coca-cola", "pepsi", "sprite", "fanta",
                "mountain dew", "7up", "mirinda", "thums up",
                "limca", "soft drink", "cola", "soda",
                "carbonated", "soda water",
            ],
            "Juices": [
                "juice", "fruit juice", "mixed fruit juice",
                "mango juice", "apple juice", "orange juice",
                "real fruit juice", "tropicana", "minute maid",
                "squash", "syrup", "concentrate", "fruit drink",
                "paper boat",
            ],
            "Tea": [
                "tea", "chai", "green tea", "black tea",
                "tata tea", "red label", "taj mahal", "lipton",
                "herbal tea", "detox tea", "ice tea",
            ],
            "Coffee": [
                "coffee", "nescafe", "bru", "filter coffee",
                "instant coffee", "cold coffee", "frappe",
                "espresso", "cappuccino", "latte",
            ],
            "Energy Drinks": [
                "energy drink", "red bull", "monster energy",
                "sting energy", "glucon-d", "sports drink",
                "electrolyte", "ORS", "gatorade",
            ],
            "Water": [
                "bottled water", "mineral water", "spring water",
                "coconut water", "tender coconut water",
            ],
        },
    },
    "Snacks": {
        "description": "Chips, namkeen, biscuits, chocolates, noodles, popcorn, and ready-to-eat snacks.",
        "icon": "bi-bag",
        "sort_order": 6,
        "primary_keywords": [
            "chips", "potato chips", "tortilla chips", "nachos",
            "lays", "kurkure", "bingo", "mad angles", "doritos",
            "pita chips", "veggie chips",
            "namkeen", "bhujia", "bikaneri bhujia", "sev",
            "chana jor", "chana", "murmura", "puffed rice",
            "mixture", "chevda", "chivda",
            "popcorn", "cheese balls", "puffs",
            "biscuit", "cookie", "cracker", "rusk", "toast",
            "marie gold", "jim jam", "bourbon", "nice time",
            "good day", "parle-g", "oreo", "hide & seek",
            "chocolate", "dairy milk", "kitkat", "five star",
            "ferrero rocher", "snickers", "m&m", "twix",
            "milky bar", "bournvita", "cadbury", "nestle chocolate",
            "dark chocolate", "white chocolate",
            "noodle", "maggi", "top ramen", "yippee",
            "cup noodle", "instant noodle", "pasta",
            "instant pasta", "ready to eat", "instant food",
            "ramen", "vermicelli", "sevai",
            "frozen snack", "frozen pizza", "frozen paratha",
            "samosa", "spring roll", "cutlet",
        ],
        "secondary_keywords": [
            "snack", "munch", "crunchy", "spicy", "tangy",
            "instant", "ready to eat", "packaged",
            "party snack", "tea time",
        ],
        "brand_keywords": [
            "lays", "kurkure", "bingo", "parle",
            "cadbury", "nestle", "ferrero", "haldiram",
            "bikaji", "bikanervala", "maggi", "top ramen",
            "yippee", "oreo", "sunfeast",
        ],
        "exclude_keywords": [
            "soap", "shampoo", "detergent", "milk", "fresh fruit",
            "fresh vegetable", "toothpaste",
        ],
        "subcategory_rules": {
            "Chips": [
                "chips", "potato chips", "tortilla chips", "nachos",
                "lays", "kurkure", "bingo", "mad angles", "doritos",
            ],
            "Namkeen": [
                "namkeen", "bhujia", "bikaneri bhujia", "sev",
                "chana jor", "chana", "murmura", "mixture",
                "chevda", "chivda",
            ],
            "Biscuits": [
                "biscuit", "cookie", "cracker", "rusk", "toast",
                "marie gold", "jim jam", "bourbon", "nice time",
                "parle-g", "good day", "oreo", "hide & seek",
            ],
            "Chocolates": [
                "chocolate", "dairy milk", "kitkat", "five star",
                "ferrero rocher", "snickers", "m&m", "twix",
                "milky bar", "cadbury", "nestle chocolate",
                "dark chocolate", "white chocolate",
            ],
            "Instant Food": [
                "noodle", "maggi", "top ramen", "yippee",
                "cup noodle", "instant noodle", "pasta",
                "instant pasta", "ready to eat", "instant food",
                "ramen", "vermicelli", "sevai",
            ],
            "Frozen Snacks": [
                "frozen snack", "frozen pizza", "frozen paratha",
                "samosa", "spring roll", "cutlet",
            ],
        },
    },
    "Grocery & Staples": {
        "description": "Rice, wheat flour, sugar, salt, pulses, cooking oil, spices, and other kitchen staples.",
        "icon": "bi-box-seam",
        "sort_order": 7,
        "primary_keywords": [
            "rice", "basmati", "sona masuri", "kolam", "brown rice",
            "poha", "flattened rice", "idli rice", "parboiled rice",
            "wheat flour", "atta", "maida", "besan", "gram flour",
            "chickpea flour", "rice flour", "rava", "sooji",
            "sugar", "brown sugar", "powdered sugar", "jaggery",
            "gud", "sugar substitute",
            "salt", "tata salt", "table salt", "black salt",
            "rock salt", "sendha namak", "sea salt", "pink salt",
            "pulse", "dal", "toor dal", "arhar dal", "moong dal",
            "masoor dal", "chana dal", "urad dal", "split dal",
            "rajma", "kidney beans", "chickpea", "kabuli chana",
            "black chana", "brown chana", "chole", "lobia",
            "black eyed peas", "soybean", "soya chunks",
            "cooking oil", "vegetable oil", "sunflower oil",
            "mustard oil", "olive oil", "coconut oil",
            "groundnut oil", "rice bran oil", "soybean oil",
            "sesame oil", "gingelly oil", "ghee",
            "spice", "turmeric", "haldi", "red chilli powder",
            "cumin", "jeera", "coriander powder", "dhaniya powder",
            "garam masala", "chana masala", "pav bhaji masala",
            "chicken masala", "meat masala", "kitchen king masala",
            "pepper", "black pepper", "cardamom", "elaichi",
            "cinnamon", "dalchini", "clove", "laung",
            "nutmeg", "jaiphal", "mace", "javitri",
            "bay leaf", "tej patta", "fennel", "saunf",
            "mustard seeds", "rai", "fenugreek seeds", "methi seeds",
            "cooking soda", "baking soda", "baking powder",
            "yeast", "gelatin", "cornflour", "corn starch",
            "vinegar", "soy sauce", "chilli sauce", "tomato sauce",
            "ketchup", "mayonnaise", "salad dressing",
            "jam", "marmalade", "honey", "maple syrup",
            "pickle", "achar", "mango pickle", "lemon pickle",
            "oats", "rolled oats", "oatmeal", "cornflakes",
            "muesli", "dalia", "broken wheat", "cereal",
            "dry fruit", "almond", "badam", "cashew", "kaju",
            "walnut", "akrot", "pistachio", "pista", "raisin",
            "kishmish", "fig", "anjeer", "dates", "khajoor",
            "seeds", "chia seeds", "flax seeds", "sunflower seeds",
            "pumpkin seeds", "quinoa", "buckwheat", "millet",
            "jowar", "bajra", "ragi", "nachni",
            "tofu", "soya", "protein powder",
        ],
        "secondary_keywords": [
            "grocery", "staple", "pantry", "essential", "daily need",
            "whole grain", "organic", "bulk", "packet", "sack",
            "kg", "kilogram", "litre", "refill",
        ],
        "brand_keywords": [
            "tata", "fortune", "saffola", "patanjali", "deep",
            "dhara", "p mark", "bambino", "kohinoor",
            "daawat", "lal qila",
        ],
        "exclude_keywords": [
            "soap", "shampoo", "bread", "cake", "milk",
            "ice cream", "fresh fruit", "vegetable",
        ],
        "subcategory_rules": {
            "Rice": [
                "rice", "basmati", "sona masuri", "kolam",
                "brown rice", "poha", "flattened rice",
                "idli rice", "parboiled rice",
            ],
            "Flour": [
                "wheat flour", "atta", "maida", "besan",
                "gram flour", "chickpea flour", "rice flour",
                "rava", "sooji", "cornflour",
            ],
            "Pulses": [
                "dal", "toor dal", "arhar dal", "moong dal",
                "masoor dal", "chana dal", "urad dal",
                "rajma", "kidney beans", "chickpea",
                "kabuli chana", "chole", "lobia", "soybean",
                "soya chunks", "black eyed peas",
            ],
            "Sugar": [
                "sugar", "brown sugar", "powdered sugar",
                "jaggery", "gud", "sugar substitute", "honey",
                "maple syrup",
            ],
            "Oils": [
                "cooking oil", "vegetable oil", "sunflower oil",
                "mustard oil", "olive oil", "coconut oil",
                "groundnut oil", "rice bran oil", "sesame oil",
            ],
            "Spices": [
                "spice", "turmeric", "haldi", "red chilli powder",
                "cumin", "jeera", "coriander powder",
                "garam masala", "chana masala", "pav bhaji masala",
                "black pepper", "cardamom", "cinnamon",
                "clove", "bay leaf", "fennel", "mustard seeds",
            ],
            "Salt": [
                "salt", "tata salt", "table salt", "black salt",
                "rock salt", "sendha namak", "sea salt",
            ],
            "Condiments": [
                "vinegar", "soy sauce", "chilli sauce",
                "tomato sauce", "ketchup", "mayonnaise",
                "jam", "marmalade", "pickle", "achar",
            ],
            "Cereals": [
                "oats", "rolled oats", "cornflakes", "muesli",
                "dalia", "quinoa", "millet", "jowar", "bajra",
                "ragi",
            ],
        },
    },
    "Personal Care": {
        "description": "Soap, shampoo, face wash, toothpaste, lotions, deodorants, and other personal hygiene products.",
        "icon": "bi-person-heart",
        "sort_order": 8,
        "primary_keywords": [
            "soap", "bath soap", "hand wash", "liquid soap",
            "body wash", "shower gel", "face wash",
            "shampoo", "conditioner", "hair conditioner",
            "hair oil", "hair serum", "hair mask", "hair cream",
            "hair spray", "hair gel", "hair color", "hair dye",
            "toothpaste", "toothbrush", "mouthwash",
            "dental floss", "tongue cleaner",
            "lotion", "moisturizer", "cold cream", "body lotion",
            "hand cream", "face cream", "night cream",
            "sunscreen", "sunblock", "sun protection",
            "face pack", "face mask", "scrub", "face scrub",
            "body scrub", "face serum", "face toner",
            "deodorant", "deo", "body spray", "perfume",
            "cologne", "attar", "itr",
            "sanitary pad", "sanitary napkin", "tampon",
            "panty liner", "feminine hygiene",
            "talcum powder", "baby powder", "body powder",
            "shaving cream", "shaving foam", "razor",
            "shaver", "trimmer", "hair remover", "wax strip",
            "lip balm", "chapstick", "lipstick", "lip gloss",
            "kajal", "eyeliner", "mascara", "eyeshadow",
            "foundation", "compact powder", "concealer",
            "nail polish", "nail paint", "nail polish remover",
            "makeup remover", "cleansing milk",
        ],
        "secondary_keywords": [
            "personal care", "beauty", "skincare", "haircare",
            "oral care", "hygiene", "grooming", "cosmetic",
            "wellness", "self care",
        ],
        "brand_keywords": [
            "lux", "lifebuoy", "dove", "santoor", "dettol",
            "pears", "himalaya", "pond's", "nivea", "vaseline",
            "colgate", "pepsodent", "sensodyne", "closeup",
            "head & shoulders", "sunsilk", "clinic plus",
            "parachute", "garnier", "l'oreal", "lakme", "maybelline",
            "rexona", "wildstone", "park avenue",
            "set wet", "gillette", "whisper", "stayfree",
            "clear", "medimix",
        ],
        "exclude_keywords": [
            "detergent", "dish wash", "floor cleaner",
            "food", "drink", "vegetable", "fruit", "bread",
        ],
        "subcategory_rules": {
            "Soap": [
                "soap", "bath soap", "hand wash", "liquid soap",
                "body wash", "shower gel",
            ],
            "Shampoo": [
                "shampoo", "conditioner", "hair conditioner",
            ],
            "Face Wash": [
                "face wash", "face pack", "face mask",
                "face scrub", "face serum", "face toner",
            ],
            "Toothpaste": [
                "toothpaste", "toothbrush", "mouthwash",
                "dental floss",
            ],
            "Skin Care": [
                "lotion", "moisturizer", "cold cream",
                "body lotion", "face cream", "night cream",
                "sunscreen", "sunblock",
            ],
            "Hair Care": [
                "hair oil", "hair serum", "hair mask",
                "hair cream", "hair spray", "hair gel",
            ],
            "Deodorants": [
                "deodorant", "deo", "body spray", "perfume",
                "cologne", "attar",
            ],
            "Feminine Hygiene": [
                "sanitary pad", "sanitary napkin", "tampon",
                "panty liner",
            ],
        },
    },
    "Household": {
        "description": "Detergents, dish wash, floor cleaners, tissue paper, garbage bags, and home cleaning essentials.",
        "icon": "bi-house-door",
        "sort_order": 9,
        "primary_keywords": [
            "detergent", "laundry detergent", "washing powder",
            "liquid detergent", "fabric softener",
            "tide", "ariel", "surf excel", "rin",
            "dish wash", "dishwashing", "dish soap",
            "vim", "pril", "dishwasher", "dishwasher tablet",
            "floor cleaner", "lizol", "colin", "surface cleaner",
            "glass cleaner", "multipurpose cleaner",
            "toilet cleaner", "toilet brush", "harpic", "domex",
            "bathroom cleaner", "shower cleaner",
            "tissue paper", "toilet paper", "paper towel",
            "kitchen roll", "napkin", "serviette",
            "garbage bag", "trash bag", "dustbin bag",
            "bin liner", "ziplock bag", "storage bag",
            "room freshener", "air freshener", "febreze",
            "odour killer", "candle", "incense stick", "agarbatti",
            "mosquito repellent", "hit", "all out", "good knight",
            "mosquito coil", "mosquito net",
            "broom", "mop", "wiper", "duster", "dustpan",
            "cleaning cloth", "microfiber cloth", "sponge",
            "scrubber", "steel wool", "scouring pad",
            "shoe polish", "furniture polish", "wood polish",
            "leather cleaner", "silver polish",
            "aluminium foil", "butter paper", "cling film",
            "plastic wrap", "baking paper", "parchment paper",
            "matchbox", "lighter", "matchstick",
            "battery", "torch", "bulb", "fuse",
            "glue", "rubber band", "safety pin", "thread",
            "tape", "cello tape", "duct tape",
        ],
        "secondary_keywords": [
            "household", "cleaning", "home care", "kitchen",
            "bathroom", "disinfectant", "hygiene",
            "maintenance", "laundry", "wash",
        ],
        "brand_keywords": [
            "tide", "ariel", "surf excel", "rin", "vim",
            "pril", "lizol", "colin", "harpic", "domex",
            "hit", "all out", "good knight", "febreze",
        ],
        "exclude_keywords": [
            "food", "drink", "shampoo", "soap", "face wash",
            "toothpaste", "vegetable", "fruit",
        ],
        "subcategory_rules": {
            "Detergents": [
                "detergent", "laundry detergent", "washing powder",
                "liquid detergent", "fabric softener",
                "tide", "ariel", "surf excel", "rin",
            ],
            "Cleaning Supplies": [
                "dish wash", "vim", "pril", "floor cleaner",
                "lizol", "colin", "glass cleaner", "surface cleaner",
                "toilet cleaner", "harpic", "domex",
                "bathroom cleaner", "sponge", "scrubber",
                "steel wool", "cleaning cloth",
            ],
            "Kitchen Essentials": [
                "tissue paper", "paper towel", "kitchen roll",
                "aluminium foil", "butter paper", "cling film",
                "ziplock bag", "garbage bag", "trash bag",
                "baking paper",
            ],
            "Home Care": [
                "room freshener", "air freshener", "febreze",
                "mosquito repellent", "hit", "all out",
                "good knight", "broom", "mop", "duster",
                "shoe polish", "furniture polish",
            ],
        },
    },
    "Frozen Foods": {
        "description": "Frozen vegetables, frozen snacks, ice cream, and other frozen food products.",
        "icon": "bi-snow",
        "sort_order": 10,
        "primary_keywords": [
            "frozen", "frozen food", "frozen vegetable",
            "frozen peas", "frozen corn", "frozen spinach",
            "frozen mixed vegetable", "frozen green bean",
            "frozen snack", "frozen pizza", "frozen paratha",
            "frozen samosa", "frozen spring roll",
            "frozen chicken", "frozen fish", "frozen seafood",
            "frozen shrimp", "frozen meat",
            "frozen biryani", "frozen meal", "frozen dinner",
            "frozen french fries", "frozen nugget",
            "frozen patty", "frozen burger",
            "ice cream", "kulfi", "gelato", "sorbet", "sherbet",
            "frozen yogurt", "frozen dessert",
            "ice cream cone", "ice cream bar", "ice cream tub",
            "magnum", "cornetto", "feast", "black forest",
            "ice cream brick", "ice cream cup",
            "frozen fruit", "frozen berry", "frozen mango",
            "frozen pastry", "frozen puff",
        ],
        "secondary_keywords": [
            "frozen", "ice cream", "cold storage",
            "chilled", "freeze", "freezer",
        ],
        "brand_keywords": [
            "magnum", "cornetto", "feast", "amul frozen",
            "havmor", "kwality walls", "baskin robbins",
            "naturals", "ibaco", "creame bell",
            "greenfield", "safal",
        ],
        "exclude_keywords": [
            "fresh vegetable", "fresh fruit", "milk", "bread",
            "soap", "shampoo",
        ],
        "subcategory_rules": {
            "Ice Cream": [
                "ice cream", "kulfi", "gelato", "sorbet",
                "sherbet", "frozen yogurt", "frozen dessert",
                "ice cream cone", "ice cream bar", "ice cream tub",
                "magnum", "cornetto", "feast",
            ],
            "Frozen Vegetables": [
                "frozen vegetable", "frozen peas", "frozen corn",
                "frozen spinach", "frozen mixed vegetable",
                "frozen fruit", "frozen berry",
            ],
            "Frozen Snacks": [
                "frozen snack", "frozen pizza", "frozen paratha",
                "frozen samosa", "frozen spring roll",
                "frozen french fries", "frozen nugget",
                "frozen patty", "frozen pastry",
            ],
            "Frozen Meat": [
                "frozen chicken", "frozen fish", "frozen seafood",
                "frozen shrimp", "frozen meat",
            ],
        },
    },
}

BRAND_TO_CATEGORY = {}
for cat_name, cat_data in CATEGORY_RULES.items():
    for brand in cat_data.get("brand_keywords", []):
        brand_lower = brand.lower()
        if brand_lower not in BRAND_TO_CATEGORY:
            BRAND_TO_CATEGORY[brand_lower] = cat_name

SUBCATEGORY_TO_CATEGORY = {}
for cat_name, cat_data in CATEGORY_RULES.items():
    for sub_name in cat_data.get("subcategory_rules", {}).keys():
        SUBCATEGORY_TO_CATEGORY[sub_name] = cat_name

ALL_CATEGORY_NAMES = set(CATEGORY_RULES.keys())
ALL_EXCLUDE_KEYWORDS = {}
for cat_name, cat_data in CATEGORY_RULES.items():
    ALL_EXCLUDE_KEYWORDS[cat_name] = cat_data.get("exclude_keywords", [])


# ============================================================
# AUDIT LOG
# ============================================================

AUDIT_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "classification_audit.log")


def log_audit(message):
    """Write a timestamped audit entry to the log file and logger."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    logger.info(line)
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ============================================================
# KEYWORD MATCHING HELPERS
# ============================================================

# Precompile exclude-keyword patterns per category for performance
import re as _re


def _normalize(text):
    return text.lower().replace("'", "").replace("-", " ").replace("\u2019", "")


def _has_keyword(text, keyword):
    normalized_text = _normalize(text)
    normalized_keyword = _normalize(keyword)
    pattern = r'\b' + _re.escape(normalized_keyword) + r'(?:es|s)?\b'
    return bool(_re.search(pattern, normalized_text))


def _has_any_keyword(text, keywords):
    for kw in keywords:
        if _has_keyword(text, kw):
            return True
    return False


def _count_keyword_matches(text, keywords):
    matched = set()
    for kw in keywords:
        if _has_keyword(text, kw):
            matched.add(kw.lower())
    return len(matched)


# ============================================================
# CLASSIFIER
# ============================================================

class ProductClassifier:
    """Classifies products into categories based on keyword, brand, and payload analysis."""

    def __init__(self):
        self.category_rules = CATEGORY_RULES
        self.brand_to_category = BRAND_TO_CATEGORY
        self.subcategory_rules = SUBCATEGORY_TO_CATEGORY
        self.exclude_keywords = ALL_EXCLUDE_KEYWORDS
        self.all_category_names = ALL_CATEGORY_NAMES

    def classify(self, product):
        """
        Classify a product and return (category_name, subcategory_name, confidence_score).

        Returns (None, None, 0.0) if confidence is below threshold or no match.
        """
        full_text = self._get_product_text(product)
        full_lower = _normalize(full_text)
        title_lower = _normalize(product.title or "")

        # Brand signals from full text
        brand_boost = self._check_brand_signals(full_lower)

        best_category = None
        best_subcategory = None
        best_score = 0.0

        for category_name, rules in self.category_rules.items():
            score = self._calculate_score(full_lower, rules)

            # Apply brand boost
            if category_name in brand_boost:
                score += brand_boost[category_name]

            # Apply exclusion penalty only if exclude keyword appears in title
            if _has_any_keyword(title_lower, rules.get("exclude_keywords", [])):
                score *= 0.2

            if score > best_score:
                best_score = score
                best_category = category_name
                best_subcategory = self._find_best_subcategory(full_lower, rules)

        if best_score < 0.1:
            return None, None, 0.0

        return best_category, best_subcategory, best_score

    def _get_product_text(self, product):
        """Combine all product text fields for analysis, including api_payload."""
        parts = [
            product.title or "",
            product.description or "",
            product.origin or "",
            product.weight or "",
            product.availability or "",
        ]
        if product.highlights:
            parts.extend(str(h) for h in product.highlights)
        if product.nutrition_info:
            parts.extend(str(v) for v in product.nutrition_info.values())
        if product.api_payload:
            payload = product.api_payload
            for field in ["title", "name", "description", "brand", "brand_name",
                          "tags", "keywords", "category", "type", "product_type",
                          "attributes", "specifications"]:
                val = payload.get(field)
                if val:
                    if isinstance(val, list):
                        parts.extend(str(v) for v in val)
                    elif isinstance(val, dict):
                        parts.extend(str(v) for v in val.values())
                    else:
                        parts.append(str(val))
            tags = payload.get("tags", [])
            if isinstance(tags, list):
                parts.extend(str(t) for t in tags)
            keywords = payload.get("keywords", [])
            if isinstance(keywords, list):
                parts.extend(str(k) for k in keywords)
        return " ".join(parts)

    def _check_brand_signals(self, text_lower):
        """Identify brand names in text and return category boosts."""
        boosts = defaultdict(float)
        for brand, cat in self.brand_to_category.items():
            if _has_keyword(text_lower, brand):
                boosts[cat] += 1.5
        return boosts

    def _calculate_score(self, text_lower, rules):
        """Calculate relevance score for a category based on keyword matches."""
        primary_keywords = rules.get("primary_keywords", [])
        secondary_keywords = rules.get("secondary_keywords", [])

        primary_matches = _count_keyword_matches(text_lower, primary_keywords)
        secondary_matches = _count_keyword_matches(text_lower, secondary_keywords)

        score = (primary_matches * 2.0) + (secondary_matches * 0.5)

        word_count = len(text_lower.split())
        if word_count > 0:
            score = score / max(word_count ** 0.5, 1.0)

        return score

    def _find_best_subcategory(self, text_lower, rules):
        """Find the best matching subcategory within a category."""
        subcategory_rules = rules.get("subcategory_rules", {})
        if not subcategory_rules:
            return None

        best_sub = None
        best_sub_score = 0.0

        for sub_name, keywords in subcategory_rules.items():
            matches = _count_keyword_matches(text_lower, keywords)
            if matches > best_sub_score:
                best_sub_score = matches
                best_sub = sub_name

        return best_sub

    def detect_misclassified(self, product):
        """
        Check if a product is currently assigned to a category that is clearly wrong.
        Returns (is_misclassified, suggested_category) tuple.
        """
        if not product.category:
            return True, None

        current_cat_name = product.category.name
        if current_cat_name not in self.all_category_names:
            return False, None

        full_text = self._get_product_text(product)
        full_lower = _normalize(full_text)
        title_lower = _normalize(product.title or "")

        rules = self.category_rules.get(current_cat_name, {})
        current_score = self._calculate_score(full_lower, rules)

        exclude = rules.get("exclude_keywords", [])
        if _has_any_keyword(title_lower, exclude) and current_score < 0.5:
            best_cat, best_sub, best_conf = self.classify(product)
            return True, best_cat

        if current_score < 0.05 and self._has_strong_signal_for_other(full_lower, current_cat_name):
            best_cat, best_sub, best_conf = self.classify(product)
            return True, best_cat

        return False, None

    def _has_strong_signal_for_other(self, text_lower, exclude_category):
        for cat_name, rules in self.category_rules.items():
            if cat_name == exclude_category:
                continue
            score = self._calculate_score(text_lower, rules)
            if score >= 1.0:
                return True
        return False


class ClassificationReport:
    """Collects and formats classification statistics."""

    def __init__(self):
        self.total_scanned = 0
        self.categorized_successfully = 0
        self.manual_review_needed = 0
        self.already_correct = 0
        self.reclassified = 0
        self.new_categories_created = 0
        self.errors = 0
        self.misclassified_fixed = 0
        self.categories_found = set()
        self.changes = []
        self.manual_review_products = []

    def add_success(self, product, old_cat, new_cat, old_sub, new_sub, confidence, is_new):
        self.categorized_successfully += 1
        self.reclassified += 1
        self.categories_found.add(new_cat)
        if is_new:
            self.new_categories_created += 1
        self.changes.append({
            "product_id": product.id,
            "product_title": product.title[:60],
            "old_category": old_cat,
            "new_category": new_cat,
            "old_subcategory": old_sub,
            "new_subcategory": new_sub,
            "confidence": round(confidence, 2),
        })

    def add_manual_review(self, product, reason):
        self.manual_review_needed += 1
        self.manual_review_products.append({
            "product_id": product.id,
            "product_title": product.title[:60],
            "reason": reason,
        })

    def print_report(self, write_func, dry_run):
        write_func("=" * 70)
        write_func("  CLASSIFICATION REPORT")
        write_func("=" * 70)

        lines = [
            ("Products Scanned", self.total_scanned),
            ("Categories Found", len(self.categories_found)),
            ("New Categories Created", self.new_categories_created),
            ("Already Correctly Placed", self.already_correct),
            ("Products Reclassified", self.reclassified),
            ("Misclassified Assignments Fixed", self.misclassified_fixed),
            ("Categorized Successfully", self.categorized_successfully),
            ("Manual Review Needed", self.manual_review_needed),
            ("Errors", self.errors),
        ]
        for label, value in lines:
            write_func(f"  {label:<45} {value}")

        if not dry_run and self.changes:
            write_func("-" * 70)
            write_func("  CATEGORY DISTRIBUTION (After Changes):")
            write_func("-" * 70)
            from django.db.models import Count
            distribution = Product.objects.values("category__name").annotate(
                count=Count("id")
            ).order_by("-count")
            for item in distribution:
                name = item["category__name"] or "Uncategorized"
                count = item["count"]
                write_func(f"    {name}: {count}")

        if self.changes:
            write_func("-" * 70)
            write_func("  RECLASSIFIED PRODUCTS (first 30):")
            write_func("-" * 70)
            for c in self.changes[:30]:
                write_func(
                    f"  ID:{c['product_id']:<5} {c['product_title'][:36]:<36} | "
                    f"{c['old_category'] or 'None':<18} -> {c['new_category']:<18} | "
                    f"Conf: {c['confidence']:.2f}"
                )
            if len(self.changes) > 30:
                write_func(f"  ... and {len(self.changes) - 30} more")

        if self.manual_review_products:
            write_func("-" * 70)
            write_func("  PRODUCTS REQUIRING MANUAL REVIEW (first 20):")
            write_func("-" * 70)
            for item in self.manual_review_products[:20]:
                write_func(
                    f"  ID:{item['product_id']:<5} {item['product_title'][:42]:<42} | "
                    f"Reason: {item['reason']}"
                )
            if len(self.manual_review_products) > 20:
                write_func(f"  ... and {len(self.manual_review_products) - 20} more")

        write_func("=" * 70)


# ============================================================
# COMMAND
# ============================================================

class Command(BaseCommand):
    help = "Automatically classify products into the most appropriate categories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without modifying the database.",
        )
        parser.add_argument(
            "--create-missing-categories",
            action="store_true",
            help="Automatically create categories that don't exist.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of products per batch (default: 100).",
        )
        parser.add_argument(
            "--min-confidence",
            type=float,
            default=0.15,
            help="Minimum confidence score to auto-assign (default: 0.15).",
        )
        parser.add_argument(
            "--fix-misclassified",
            action="store_true",
            help="Also fix products clearly assigned to wrong categories.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        create_missing = options["create_missing_categories"]
        batch_size = options["batch_size"]
        min_confidence = options["min_confidence"]
        fix_misclassified = options["fix_misclassified"]

        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE("  PRODUCT AUTO-CLASSIFICATION SYSTEM"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN MODE - No changes will be saved."))
        if fix_misclassified:
            self.stdout.write(self.style.WARNING("  MISCLASSIFICATION FIX MODE - Will reassign wrongly categorized products."))

        log_audit("=" * 70)
        log_audit("CLASSIFICATION RUN STARTED" + (" (DRY RUN)" if dry_run else ""))
        log_audit("=" * 70)

        classifier = ProductClassifier()
        report = ClassificationReport()

        products = Product.objects.select_related(
            "category", "subcategory", "subsubcategory"
        ).all()

        total_products = products.count()
        self.stdout.write(f"\n  Total products to scan: {total_products}\n")
        log_audit(f"Total products to scan: {total_products}")

        for i in range(0, total_products, batch_size):
            batch = products[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_products + batch_size - 1) // batch_size

            self.stdout.write(
                f"  Processing batch {batch_num}/{total_batches} "
                f"(products {i + 1}-{min(i + batch_size, total_products)})..."
            )

            for product in batch:
                report.total_scanned += 1

                try:
                    # Phase A: Detect misclassified products (if enabled)
                    if fix_misclassified:
                        is_misclassified, suggested_cat = classifier.detect_misclassified(product)
                        if is_misclassified:
                            if suggested_cat:
                                target_cat, cat_created = self._get_or_create_category(
                                    suggested_cat, create_missing
                                )
                                if target_cat:
                                    old_cat = product.category.name if product.category else None
                                    old_sub = product.subcategory.name if product.subcategory else None
                                    self._record_and_apply(
                                        product, target_cat, None, old_cat, old_sub,
                                        0.8, cat_created, report, dry_run
                                    )
                                    report.misclassified_fixed += 1
                                    log_audit(
                                        f"FIXED misclassified product {product.id} "
                                        f"'{product.title}': {old_cat or 'None'} -> {suggested_cat}"
                                    )
                                    continue
                            else:
                                report.add_manual_review(product, "Misclassified - no good match found")
                                continue

                    # Phase B: Normal classification
                    suggested_category_name, suggested_subcategory_name, confidence = classifier.classify(product)

                    if suggested_category_name is None or confidence < min_confidence:
                        report.add_manual_review(
                            product,
                            f"Low confidence ({confidence:.2f})"
                        )
                        continue

                    target_category, cat_created = self._get_or_create_category(
                        suggested_category_name, create_missing
                    )

                    if target_category is None:
                        report.add_manual_review(
                            product,
                            f"Category '{suggested_category_name}' not found "
                            f"and --create-missing-categories not set"
                        )
                        continue

                    if cat_created:
                        self.stdout.write(
                            self.style.SUCCESS(f"    Created new category: {target_category.name}")
                        )
                        log_audit(f"Created new category: {target_category.name}")

                    target_subcategory = None
                    if suggested_subcategory_name:
                        target_subcategory, sub_created = self._get_or_create_subcategory(
                            target_category, suggested_subcategory_name, create_missing
                        )

                    old_cat = product.category.name if product.category else None
                    old_sub = product.subcategory.name if product.subcategory else None

                    needs_update = (
                        product.category_id != target_category.id or
                        (target_subcategory and product.subcategory_id != target_subcategory.id) or
                        (not target_subcategory and product.subcategory_id is not None)
                    )

                    if not needs_update:
                        report.already_correct += 1
                        report.categorized_successfully += 1
                        report.categories_found.add(target_category.name)
                        continue

                    self._record_and_apply(
                        product, target_category, target_subcategory,
                        old_cat, old_sub, confidence, cat_created,
                        report, dry_run
                    )

                    log_audit(
                        f"Reclassified product {product.id} '{product.title}': "
                        f"{old_cat or 'None'} -> {target_category.name} | "
                        f"Confidence: {confidence:.2f}"
                    )

                except Exception as e:
                    report.errors += 1
                    logger.exception(f"Error processing product {product.id}: {e}")
                    self.stdout.write(
                        self.style.ERROR(f"    Error processing '{product.title}': {e}")
                    )

        self.stdout.write("\n")
        w = lambda msg: self.stdout.write(self.style.NOTICE(msg))
        report.print_report(w, dry_run)

        log_audit("-" * 70)
        log_audit(
            f"Products Scanned: {report.total_scanned} | "
            f"Categories Found: {len(report.categories_found)} | "
            f"New Categories Created: {report.new_categories_created} | "
            f"Categorized Successfully: {report.categorized_successfully} | "
            f"Manual Review Needed: {report.manual_review_needed}"
        )
        log_audit("CLASSIFICATION RUN COMPLETED" + (" (DRY RUN)" if dry_run else ""))
        log_audit("=" * 70)

        if dry_run:
            self.stdout.write(self.style.NOTICE("\n  DRY RUN COMPLETE - No changes were saved."))
        else:
            self.stdout.write(self.style.NOTICE("\n  CLASSIFICATION COMPLETE"))
        self.stdout.write(self.style.NOTICE("=" * 70 + "\n"))

    def _record_and_apply(self, product, target_cat, target_sub, old_cat, old_sub,
                          confidence, cat_created, report, dry_run):
        report.add_success(
            product, old_cat, target_cat.name,
            old_sub, target_sub.name if target_sub else None,
            confidence, cat_created
        )
        if not dry_run:
            product.category = target_cat
            product.subcategory = target_sub
            product.save(update_fields=["category", "subcategory"])

    def _get_or_create_category(self, category_name, create_missing):
        try:
            return Category.objects.get(name=category_name), False
        except Category.DoesNotExist:
            if create_missing:
                rule = CATEGORY_RULES.get(category_name, {})
                category = Category.objects.create(
                    name=category_name,
                    description=rule.get(
                        "description",
                        f"Auto-created category for {category_name.lower()} products."
                    ),
                    icon=rule.get("icon", ""),
                    is_active=True,
                    sort_order=rule.get("sort_order", Category.objects.count() + 1),
                )
                return category, True
            return None, False

    def _get_or_create_subcategory(self, category, subcategory_name, create_missing):
        try:
            return Subcategory.objects.get(name=subcategory_name, category=category), False
        except Subcategory.DoesNotExist:
            if create_missing:
                subcategory = Subcategory.objects.create(
                    name=subcategory_name,
                    category=category,
                    is_active=True,
                    sort_order=category.subcategories.count() + 1,
                )
                return subcategory, True
            return None, False
