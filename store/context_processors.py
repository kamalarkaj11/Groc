from django.http import HttpRequest
from .models import CartItem


def cart_context(request: HttpRequest) -> dict:
    """
    Context processor to add cart item count to all templates.
    Returns 0 for anonymous users.
    """
    if request.user.is_authenticated:
        count = CartItem.objects.filter(user=request.user).count()
    else:
        count = 0
    return {'cart_item_count': count}



