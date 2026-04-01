from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from campaign_management.publisher_auth import is_publisher_session


def _campaign_context_from_request(request):
    return (
        request.GET.get("campaign")
        or request.GET.get("brand_campaign_id")
        or request.POST.get("campaign")
        or request.POST.get("brand_campaign_id")
        or getattr(request, "session", {}).get("brand_campaign_id")
        or ""
    ).strip()


def _fieldrep_login_redirect(request):
    params = []
    campaign = _campaign_context_from_request(request)
    if campaign:
        params.append(("campaign", campaign))

    login_url = reverse("fieldrep_gmail_login")
    if params:
        login_url = f"{login_url}?{urlencode(params)}"

    messages.error(request, "Please Login to continue")
    return redirect(login_url)


def _management_login_redirect(request):
    params = [("next", request.get_full_path())]
    campaign = _campaign_context_from_request(request)
    if campaign:
        params.append(("campaign", campaign))

    messages.error(request, "Please log in to continue.")
    return redirect(f"{reverse('admin_login')}?{urlencode(params)}")


def field_rep_required(view_func):
    """
    Decorator to ensure only authenticated field reps reach rep-only views.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and getattr(user, "role", "") == "field_rep":
            return view_func(request, *args, **kwargs)
        return _fieldrep_login_redirect(request)

    return _wrapped_view


def dashboard_access_required(view_func):
    """
    Dashboard management pages are opened from admin/publisher flows, not just field-rep sessions.
    Allow:
      - normal logged-in Django users
      - publisher SSO sessions
      - field-rep session bootstrap used by the Gmail login flow
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return view_func(request, *args, **kwargs)

        if is_publisher_session(request):
            return view_func(request, *args, **kwargs)

        session = getattr(request, "session", None) or {}
        if session.get("field_rep_email") and session.get("field_rep_id"):
            return view_func(request, *args, **kwargs)

        return _management_login_redirect(request)

    return _wrapped_view
