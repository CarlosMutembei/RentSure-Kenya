from django import template

register = template.Library()

@register.filter
def model_name(obj):
    """Returns the verbose name of the model for the given object."""
    if obj is None:
        return ''
    # Use Django's built-in verbose_name
    return obj._meta.verbose_name.title()