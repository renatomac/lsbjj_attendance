from django import template

register = template.Library()

@register.filter
def repeat(value, times):
    """Repeat a string a number of times"""
    if not value or not times:
        return ''
    try:
        return value * int(times)
    except (ValueError, TypeError):
        return ''
