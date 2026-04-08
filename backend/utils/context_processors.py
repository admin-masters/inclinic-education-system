from django.conf import settings
from django.urls import reverse
from urllib.parse import urlsplit


def recaptcha_site_key(request):
    return {'RECAPTCHA_SITE_KEY': settings.RECAPTCHA_SITE_KEY}


def _support_widget_proxy_url(request, raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        return ""

    parsed = urlsplit(value)
    remote_path = (parsed.path or "").lstrip("/")
    if not remote_path:
        return ""

    proxy_url = reverse("support_widget_proxy", kwargs={"remote_path": remote_path})
    if parsed.query:
        return f"{proxy_url}?{parsed.query}"
    return proxy_url


def _support_widget_target(request):
    path = (getattr(request, "path", "") or "").lower()
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") or ""
    namespace = getattr(resolver_match, "namespace", "") or ""

    if url_name == "doctor_collateral_verify":
        return "doctor", "doctor_verify"
    if url_name in {"doctor_collateral_view", "doctor_view"}:
        return "doctor", "doctor_view"
    if url_name in {"doctor_view_report", "tracking_dashboard"}:
        return "doctor", "doctor_reports"

    if url_name in {"share_content", "share_success"}:
        return "clinic_staff", "clinic_staff_sharing"
    if url_name == "share_logs":
        return "clinic_staff", "clinic_staff_reports"

    if url_name == "fieldrep_gmail_login":
        return "field_rep", "field_rep_gmail_login"
    if url_name in {
        "fieldrep_login",
        "fieldrep_forgot_password",
        "fieldrep_reset_password",
        "fieldrep_email_registration",
        "fieldrep_create_password",
    }:
        return "field_rep", "field_rep_authentication"
    if url_name in {
        "fieldrep_share_collateral",
        "fieldrep_share_collateral_by_campaign",
        "fieldrep_gmail_share_collateral",
        "fieldrep_gmail_share_collateral_by_campaign",
    }:
        return "field_rep", "field_rep_share_collaterals"

    brand_manager_names = {
        "manage_data_panel",
        "campaign_list",
        "campaign_detail",
        "campaign_update",
        "campaign_by_id_detail",
        "campaign_by_id_update",
        "publisher_campaign_update",
        "campaign_create",
        "campaign_delete",
        "publisher_landing_page",
        "publisher_campaign_select",
        "campaign_thank_you",
        "fieldrep_dashboard",
        "fieldrep_campaign_detail",
        "doctor_list",
        "campaign_doctor_list",
        "doctor_bulk_upload",
        "doctor_bulk_upload_sample",
        "dashboard_delete_collateral",
        "edit_collateral_dates",
        "edit_campaign_calendar",
        "video_tracking",
        "debug_collaterals",
    }

    if url_name in {"collateral_transactions_dashboard"} or path.startswith("/reports/"):
        return "brand_manager", "brand_manager_reports"
    if url_name in {"home"} or path.startswith("/admin/login/"):
        return "brand_manager", "brand_manager_authentication"
    if url_name in brand_manager_names or namespace in {"admin_dashboard", "admin-dashboard"}:
        return "brand_manager", "brand_manager_campaign_operations"
    if path.startswith("/campaigns/") or path.startswith("/admin_dashboard/") or path.startswith("/publisher/"):
        return "brand_manager", "brand_manager_campaign_operations"
    if path.startswith("/collaterals/") or path.startswith("/shortlinks/") or path.startswith("/share/dashboard/"):
        return "brand_manager", "brand_manager_campaign_operations"
    if path.startswith("/share/fieldrep"):
        return "field_rep", "field_rep_share_collaterals"
    if path.startswith("/view/"):
        return "doctor", "doctor_view"
    if path.startswith("/patient/"):
        return "patient", "patient_video_page"
    return "", ""


def support_widget(request):
    screen_urls = getattr(settings, "SUPPORT_WIDGET_SCREEN_URLS", {}) or {}
    support_urls = getattr(settings, "SUPPORT_WIDGET_URLS", {}) or {}
    support_labels = getattr(settings, "SUPPORT_WIDGET_LABELS", {}) or {}
    role, screen = _support_widget_target(request)
    url = (screen_urls.get(screen) or support_urls.get(role) or "").strip()

    return {
        "support_widget_enabled": bool(url),
        "support_widget_role": role,
        "support_widget_screen": screen,
        "support_widget_label": support_labels.get(role, "Support"),
        "support_widget_url": url,
        "support_widget_proxy_url": _support_widget_proxy_url(request, url),
    }
