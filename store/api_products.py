import logging
import hashlib
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError
from django.utils.text import slugify

from services import grocery_api
from .models import Category, Product

logger = logging.getLogger(__name__)

CATEGORY_QUERIES = {
    "fruits": "fruits",
    "vegetables": "vegetable",
    "dairy": "dairy products",
    "snacks": "snacks",
    "beverages": "beverages",
    "bakery": "bakery",
    "grocery": "grocery",
}


def _unique_slug(title, product=None):
    base_slug = slugify(title)[:45] or "product"
    slug = base_slug
    counter = 1
    queryset = Product.objects.filter(slug=slug)
    if product and product.pk:
        queryset = queryset.exclude(pk=product.pk)
    while queryset.exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
        queryset = Product.objects.filter(slug=slug)
        if product and product.pk:
            queryset = queryset.exclude(pk=product.pk)
    return slug


def _category_for(name):
    category_name = (name or "Grocery").strip()[:100]
    slug = slugify(category_name) or "grocery"
    category, _ = Category.objects.get_or_create(
        slug=slug,
        defaults={
            "name": category_name.title(),
            "description": f"Products imported from the grocery API for {category_name}.",
            "icon": "bi-basket2",
            "is_active": True,
        },
    )
    return category


def upsert_api_product(data):
    category = _category_for(data.get("category_name"))
    defaults = {
        "title": data["title"][:200],
        "description": data.get("description") or data["title"],
        "price": data.get("price") or Decimal("0.00"),
        "discount_price": data.get("discount_price"),
        "external_image_url": data.get("external_image_url", ""),
        "category": category,
        "availability": data.get("availability", ""),
        "is_out_of_stock": data.get("is_out_of_stock", False),
        "api_rating": data.get("api_rating"),
        "api_review_count": data.get("api_review_count", 0),
        "api_payload": data.get("api_payload", {}),
    }
    product = Product.objects.filter(
        api_source=data["api_source"],
        api_product_id=data["api_product_id"],
    ).first()
    if product:
        for field, value in defaults.items():
            setattr(product, field, value)
        product.slug = _unique_slug(product.title, product)
        product.save()
        return product

    defaults.update({
        "api_source": data["api_source"],
        "api_product_id": data["api_product_id"],
        "slug": _unique_slug(data["title"]),
    })
    try:
        return Product.objects.create(**defaults)
    except IntegrityError:
        logger.exception("Unable to import API product %s", data.get("title"))
        return None


def sync_products_for_query(query, page=1, limit=24):
    query = (query or "grocery").strip()
    page = max(int(page or 1), 1)
    sync_hash = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()[:24]
    sync_key = f"grocery_api_sync:{sync_hash}:{page}:{limit}"
    cached_count = cache.get(sync_key)
    if cached_count is not None:
        return []

    imported = []
    for item in grocery_api.search_products(query, page=page)[:limit]:
        product = upsert_api_product(item)
        if product:
            imported.append(product)
    cache.set(sync_key, len(imported), 60 * 10 if not imported else 60 * 30)
    return imported


def warm_home_products():
    imported = []
    for query in ("vegetable", "fruits", "dairy products", "snacks"):
        imported.extend(sync_products_for_query(query, limit=8))
    return imported
