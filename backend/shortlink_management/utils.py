# shortlink_management/utils.py
import random, string

def generate_short_code(length=8):
    """Generate a random alphanumeric short code."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))