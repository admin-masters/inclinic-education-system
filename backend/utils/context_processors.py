from django.conf import settings


def recaptcha_site_key(request):
    return {'RECAPTCHA_SITE_KEY': settings.RECAPTCHA_SITE_KEY}


def _support_widget_target(request):
    path = (getattr(request, "path", "") or "").lower()
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") or ""

    if url_name == "doctor_collateral_verify":
        return "doctor", "doctor_verify"
    if url_name in {"doctor_collateral_view", "doctor_view"}:
        return "doctor", "doctor_view"

    if url_name == "fieldrep_gmail_login":
        return "field_rep", "field_rep_gmail_login"
    if url_name in {
        "fieldrep_login",
        "fieldrep_forgot_password",
        "fieldrep_reset_password",
        "fieldrep_email_registration",
        "fieldrep_create_password",
    }:
        return "field_rep", "field_rep_gmail_login"
    if url_name in {
        "fieldrep_share_collateral",
        "fieldrep_share_collateral_by_campaign",
        "fieldrep_gmail_share_collateral",
        "fieldrep_gmail_share_collateral_by_campaign",
    }:
        return "field_rep", "field_rep_share_collaterals"

    if path.startswith("/share/fieldrep"):
        return "field_rep", "field_rep_share_collaterals"
    if path.startswith("/view/"):
        return "doctor", "doctor_view"
    return "", ""


def support_widget(request):
    screen_urls = getattr(settings, "SUPPORT_WIDGET_SCREEN_URLS", {}) or {}
    page_urls = getattr(settings, "SUPPORT_WIDGET_PAGE_URLS", {}) or {}
    support_labels = getattr(settings, "SUPPORT_WIDGET_LABELS", {}) or {}
    role, screen = _support_widget_target(request)
    embed_url = (screen_urls.get(screen) or "").strip()
    page_url = (page_urls.get(screen) or embed_url).strip()

    return {
        "support_widget_enabled": bool(embed_url),
        "support_widget_role": role,
        "support_widget_screen": screen,
        "support_widget_label": support_labels.get(role, "Support"),
        "support_widget_url": page_url,
        "support_widget_embed_url": embed_url,
    }
