from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up a key in a dictionary. Usage: {{ mydict|get_item:key }}"""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.filter
def get_attr(obj, attr_name):
    """Get an attribute from an object. Usage: {{ obj|get_attr:'field_name' }}"""
    try:
        return getattr(obj, attr_name, None)
    except Exception:
        return None
