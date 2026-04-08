from django.conf import settings


def recaptcha_site_key(request):
    return {'RECAPTCHA_SITE_KEY': settings.RECAPTCHA_SITE_KEY}


def _support_widget_role(request):
    path = (getattr(request, "path", "") or "").lower()
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") or ""
    namespace = getattr(resolver_match, "namespace", "") or ""

    doctor_names = {
        "doctor_collateral_verify",
        "doctor_collateral_view",
        "doctor_view",
        "doctor_view_report",
        "tracking_dashboard",
    }
    field_rep_names = {
        "fieldrep_login",
        "fieldrep_forgot_password",
        "fieldrep_reset_password",
        "fieldrep_share_collateral",
        "fieldrep_share_collateral_by_campaign",
        "fieldrep_gmail_login",
        "fieldrep_gmail_share_collateral",
        "fieldrep_gmail_share_collateral_by_campaign",
        "fieldrep_email_registration",
        "fieldrep_create_password",
    }
    clinic_staff_names = {
        "share_content",
        "share_success",
        "share_logs",
    }
    brand_manager_names = {
        "home",
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
        "doctor_bulk_upload",
        "doctor_bulk_upload_sample",
        "dashboard_delete_collateral",
        "edit_collateral_dates",
        "edit_campaign_calendar",
        "video_tracking",
        "debug_collaterals",
        "collateral_transactions_dashboard",
    }

    if path.startswith("/view/") or url_name in doctor_names:
        return "doctor"
    if url_name in clinic_staff_names:
        return "clinic_staff"
    if url_name in brand_manager_names or namespace in {"admin_dashboard", "admin-dashboard"}:
        return "brand_manager"
    if path.startswith("/share/fieldrep") or url_name in field_rep_names:
        return "field_rep"
    if path.startswith("/campaigns/") or path.startswith("/admin_dashboard/") or path.startswith("/publisher/"):
        return "brand_manager"
    if path == "/" or path.startswith("/admin/login/") or path.startswith("/collaterals/") or path.startswith("/shortlinks/"):
        return "brand_manager"
    return ""


def support_widget(request):
    support_urls = getattr(settings, "SUPPORT_WIDGET_URLS", {}) or {}
    support_labels = getattr(settings, "SUPPORT_WIDGET_LABELS", {}) or {}
    role = _support_widget_role(request)
    url = (support_urls.get(role) or "").strip()

    return {
        "support_widget_enabled": bool(url),
        "support_widget_role": role,
        "support_widget_label": support_labels.get(role, "Support"),
        "support_widget_url": url,
    }
