from django.core.cache import cache
from django.db.models import Count, Q
from django.http import HttpRequest
from .models import CartItem, Category, Subcategory, SubSubCategory

CATEGORIES_CACHE_KEY = 'global_categories_context'
CATEGORIES_CACHE_TTL = 300  # 5 minutes


def cart_context(request: HttpRequest) -> dict:
    """Context processor to add cart item count to all templates."""
    if request.user.is_authenticated:
        count = CartItem.objects.filter(user=request.user).count()
    else:
        count = 0
    return {'cart_item_count': count}


def categories_context(request: HttpRequest) -> dict:
    """Context processor to make categories (with subcategories, sub-subcategories and counts)
    available in every template for navbar dropdowns, sidebar filters, etc.

    Results are cached for 5 minutes to avoid heavy DB queries on every page load.
    """
    cached = cache.get(CATEGORIES_CACHE_KEY)
    if cached is not None:
        return cached

    categories = Category.objects.prefetch_related(
        'subcategories__subsubcategories'
    ).annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).filter(is_active=True).order_by('sort_order', 'name')

    # Build a mapping of subcategory IDs to active product counts
    subcategory_ids = []
    subsubcategory_ids = []
    for cat in categories:
        for s in cat.subcategories.all():
            subcategory_ids.append(s.pk)
            subsubcategory_ids.extend([ss.pk for ss in s.subsubcategories.all()])

    sub_counts = {}
    if subcategory_ids:
        counts_qs = Subcategory.objects.filter(
            pk__in=subcategory_ids, is_active=True
        ).annotate(
            active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
        ).values('id', 'active_product_count')
        sub_counts = {item['id']: item['active_product_count'] for item in counts_qs}

    subsub_counts = {}
    if subsubcategory_ids:
        counts_qs = SubSubCategory.objects.filter(
            pk__in=subsubcategory_ids, is_active=True
        ).annotate(
            active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
        ).values('id', 'active_product_count')
        subsub_counts = {item['id']: item['active_product_count'] for item in counts_qs}

    result = {
        'global_categories': categories,
        'global_subcategory_counts': sub_counts,
        'global_subsubcategory_counts': subsub_counts,
    }

    cache.set(CATEGORIES_CACHE_KEY, result, CATEGORIES_CACHE_TTL)
    return result
