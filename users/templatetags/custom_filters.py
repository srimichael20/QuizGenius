from django import template

register = template.Library()



@register.filter
def split(value, delimiter=','):
    if value:
        return value.split(delimiter)
    return []

@register.filter
def get(dictionary, key):
    """Safely gets a value from a dictionary in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(str(key)) or dictionary.get(int(key))
    return None

@register.filter
def streak_color(count):
    if count == 0:
        return "#e0e0e0"
    elif count == 1:
        return "#90ee90"
    elif count == 2:
        return "#32cd32"
    else:
        return "#006400"    
    



@register.filter
def streak_color(count):
    """
    Returns a CSS class name based on the streak count.
    """
    if count == 0:
        return "streak-0"
    elif count == 1:
        return "streak-1"
    elif count == 2:
        return "streak-2"
    else:
        return "streak-3"