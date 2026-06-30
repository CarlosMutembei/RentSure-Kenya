from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Safely get an item from a dictionary.
    If the first argument is not a dict (or dict‑like), return None.
    """
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None