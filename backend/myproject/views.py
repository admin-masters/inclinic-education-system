from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt


def home_view(request):
    """
    Landing page that shows home.html for unauthenticated users 
    and redirects to manage data panel after login.
    """
    if request.user.is_authenticated:
        return redirect('manage_data_panel')
    return render(request, 'home.html')


def _support_proxy_base_url() -> str:
    return (getattr(settings, "SUPPORT_WIDGET_PROXY_BASE_URL", "http://65.1.101.252") or "").rstrip("/")


def _support_proxy_allowed(remote_path: str) -> bool:
    normalized = "/" + str(remote_path or "").lstrip("/")
    return normalized.startswith("/support/") or normalized.startswith("/support/api/")


def _support_proxy_destination(remote_path: str, query_string: str = "") -> str:
    if not _support_proxy_allowed(remote_path):
        raise ValueError("Unsupported support path")
    base = _support_proxy_base_url()
    path = "/" + str(remote_path or "").lstrip("/")
    if query_string:
        return f"{base}{path}?{query_string}"
    return f"{base}{path}"


def _rewrite_support_markup(body: bytes, *, proxy_prefix: str, upstream_base: str, content_type: str) -> bytes:
    if not body:
        return body

    textual_types = (
        "text/html",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/json",
    )
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type not in textual_types:
        return body

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body

    replacements = {
        f"{upstream_base}/": f"{proxy_prefix}/",
        upstream_base: proxy_prefix,
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.encode("utf-8")


@csrf_exempt
def support_widget_proxy(request, remote_path: str):
    if request.method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
        return HttpResponseNotAllowed(["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])

    if not _support_proxy_allowed(remote_path):
        return HttpResponseBadRequest("Unsupported support widget path.")

    upstream_base = _support_proxy_base_url()
    upstream_url = _support_proxy_destination(remote_path, request.META.get("QUERY_STRING", ""))

    headers = {
        "User-Agent": request.META.get("HTTP_USER_AGENT", "InclinicSupportProxy/1.0"),
        "Accept": request.META.get("HTTP_ACCEPT", "*/*"),
        "Referer": request.build_absolute_uri(request.path),
    }
    content_type = request.META.get("CONTENT_TYPE")
    if content_type:
        headers["Content-Type"] = content_type

    body = request.body if request.method in {"POST", "PUT", "PATCH"} else None
    upstream_request = Request(upstream_url, data=body, headers=headers, method=request.method)

    try:
        with urlopen(upstream_request, timeout=20) as upstream_response:
            response_body = upstream_response.read()
            response_content_type = upstream_response.headers.get("Content-Type", "text/html; charset=utf-8")
            proxy_prefix = request.build_absolute_uri("/support/chat/proxy/").rstrip("/")
            response_body = _rewrite_support_markup(
                response_body,
                proxy_prefix=proxy_prefix,
                upstream_base=upstream_base,
                content_type=response_content_type,
            )
            response = HttpResponse(
                response_body,
                status=upstream_response.getcode(),
                content_type=response_content_type,
            )
            cache_control = upstream_response.headers.get("Cache-Control")
            if cache_control:
                response["Cache-Control"] = cache_control
            return response
    except HTTPError as exc:
        error_body = exc.read()
        response_content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
        proxy_prefix = request.build_absolute_uri("/support/chat/proxy/").rstrip("/")
        error_body = _rewrite_support_markup(
            error_body,
            proxy_prefix=proxy_prefix,
            upstream_base=upstream_base,
            content_type=response_content_type,
        )
        return HttpResponse(error_body or b"Support widget request failed.", status=exc.code, content_type=response_content_type)
    except (URLError, ValueError):
        return HttpResponse("Support widget is temporarily unavailable.", status=502, content_type="text/plain; charset=utf-8")
