import requests, os
from django.conf import settings
from django.http import HttpResponseForbidden

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

def verify_recaptcha(token: str, min_score: float = 0.5) -> bool:
    data = {
        'secret': settings.RECAPTCHA_SECRET_KEY,
        'response': token,
    }
    r = requests.post(VERIFY_URL, data=data, timeout=5)
    if not r.ok:
        return False
    js = r.json()
    return js.get('success') and js.get('score', 0) >= min_score


def recaptcha_required(view):
    """
    Decorator for any POST endpoint that must include
    'g-recaptcha-token' (sent via JS).
    """
    def _wrapped(request, *args, **kw):
        if request.method == "POST":
            token = request.POST.get('g-recaptcha-token') or request.headers.get('X-Recaptcha-Token')
            if not token or not verify_recaptcha(token):
                return HttpResponseForbidden("reCAPTCHA verification failed")
        return view(request, *args, **kw)
    return _wrapped