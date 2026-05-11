from django.db.models import Count, Q
from django.http import HttpRequest
from .models import CartItem, Category, Subcategory


def cart_context(request: HttpRequest) -> dict:
    """Context processor to add cart item count to all templates."""
    if request.user.is_authenticated:
        count = CartItem.objects.filter(user=request.user).count()
    else:
        count = 0
    return {'cart_item_count': count}


def categories_context(request: HttpRequest) -> dict:
    """Context processor to make categories (with subcategories and counts)
    available in every template for navbar dropdowns, sidebar filters, etc."""
    categories = Category.objects.prefetch_related('subcategories').annotate(
        active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
    ).filter(is_active=True).order_by('sort_order', 'name')

    # Build a mapping of subcategory IDs to active product counts
    # so templates can show counts without N+1 queries.
    subcategory_ids = []
    for cat in categories:
        subcategory_ids.extend([s.pk for s in cat.subcategories.all()])

    sub_counts = {}
    if subcategory_ids:
        counts_qs = Subcategory.objects.filter(
            pk__in=subcategory_ids, is_active=True
        ).annotate(
            active_product_count=Count('products', filter=Q(products__is_out_of_stock=False))
        ).values('id', 'active_product_count')
        sub_counts = {item['id']: item['active_product_count'] for item in counts_qs}

    return {
        'global_categories': categories,
        'global_subcategory_counts': sub_counts,
    }
