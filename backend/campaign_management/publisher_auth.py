from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

import jwt
from jwt import InvalidTokenError

from django.conf import settings
from django.http import HttpRequest, HttpResponse


UNAUTH_RESPONSE_TEXT = "unauthorised access"


def _unauthorised() -> HttpResponse:
    return HttpResponse(UNAUTH_RESPONSE_TEXT, status=401)


def extract_jwt_from_request(request: HttpRequest) -> Tuple[Optional[str], str]:
    """
    Returns: (token, source)
      - source is one of: "authorization_header", "query_string", "post_body", "none"
    """
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return token, "authorization_header"

    for key in ("jwt", "token", "access_token"):
        token = request.GET.get(key)
        if token:
            return token, "query_string"

    for key in ("jwt", "token", "access_token"):
        token = request.POST.get(key)
        if token:
            return token, "post_body"

    return None, "none"


def validate_publisher_jwt(token: str) -> Dict[str, Any]:
    secret = getattr(settings, "PUBLISHER_JWT_SECRET", "") or None
    public_key = getattr(settings, "PUBLISHER_JWT_PUBLIC_KEY", "") or None
    key = public_key or secret
    if not key:
        # Treat as unauthorized (don’t leak misconfig details)
        raise InvalidTokenError("JWT verification key not configured")

    algorithms = getattr(settings, "PUBLISHER_JWT_ALGORITHMS", None) or ["HS256"]
    issuer = getattr(settings, "PUBLISHER_JWT_ISSUER", None) or "project1"
    audience = getattr(settings, "PUBLISHER_JWT_AUDIENCE", None) or "project2"
    leeway = int(getattr(settings, "PUBLISHER_JWT_LEEWAY_SECONDS", 0) or 0)

    options = {
        "require": ["exp", "iat", "iss", "aud", "sub"],
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_iss": True,
        "verify_aud": True,
    }

    payload = jwt.decode(
        token,
        key=key,
        algorithms=algorithms,
        issuer=issuer,
        audience=audience,
        options=options,
        leeway=leeway,
    )

    roles = payload.get("roles") or []
    if "publisher" not in roles:
        raise InvalidTokenError("publisher role required")

    return payload


def establish_publisher_session(request: HttpRequest, payload: Dict[str, Any]) -> None:
    # Mitigate session fixation
    try:
        request.session.cycle_key()
    except Exception:
        pass

    request.session["publisher_authenticated"] = True
    request.session["publisher_sub"] = payload.get("sub")
    request.session["publisher_username"] = payload.get("username")
    request.session["publisher_roles"] = payload.get("roles") or []
    request.session["publisher_iss"] = payload.get("iss")
    request.session["publisher_aud"] = payload.get("aud")
    request.session["publisher_jwt_iat"] = payload.get("iat")
    request.session["publisher_jwt_exp"] = payload.get("exp")

    exp = payload.get("exp")
    now = int(time.time())
    if isinstance(exp, int) and exp > now:
        request.session.set_expiry(exp - now)
    else:
        request.session.set_expiry(0)


def is_publisher_session(request: HttpRequest) -> bool:
    if not getattr(request, "session", None):
        return False
    if not request.session.get("publisher_authenticated"):
        return False
    roles = request.session.get("publisher_roles") or []
    return "publisher" in roles


def publisher_session_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        if is_publisher_session(request):
            return view_func(request, *args, **kwargs)
        return _unauthorised()

    return _wrapped


def publisher_or_login_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Allow either:
      - normal Django logged-in user (admin/staff)
      - publisher SSO session
    """
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        if getattr(request, "user", None) and request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        if is_publisher_session(request):
            return view_func(request, *args, **kwargs)
        return _unauthorised()

    return _wrapped
