from django import template

register = template.Library()


@register.filter(name="replace")
def replace(value, args):
    """
    Replace occurrences of a substring with another.

    Usage in template:
        {{ value|replace:"old,new" }}

    Example to replace underscore with space:
        {{ title|replace:"_, " }}

    The filter accepts a single argument string containing two parts
    separated by the first comma.
    """
    if value is None:
        return value
    if not isinstance(value, str):
        value = str(value)
    try:
        old, new = args.split(",", 1)
    except Exception:
        return value
    # Intentionally preserve spaces in 'new' to allow replacements like "_, "
    old = old.strip()
    return value.replace(old, new)