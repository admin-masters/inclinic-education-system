# sharing_management/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Core sharing (authenticated portal user)
    path("share/", views.share_content, name="share_content"),
    path("share/success/<int:share_log_id>/", views.share_success, name="share_success"),
    path("logs/", views.list_share_logs, name="share_logs"),

    # Field Rep Login / Password (session based)
    path("fieldrep-login/", views.fieldrep_login, name="fieldrep_login"),
    path("fieldrep-forgot-password/", views.fieldrep_forgot_password, name="fieldrep_forgot_password"),
    path("fieldrep-reset-password/", views.fieldrep_reset_password, name="fieldrep_reset_password"),

    # Field Rep Share Collateral (manual/main flow only)
    path("fieldrep-share-collateral/", views.fieldrep_share_collateral, name="fieldrep_share_collateral"),
    path(
        "fieldrep-share-collateral/<str:brand_campaign_id>/",
        views.fieldrep_share_collateral,
        name="fieldrep_share_collateral_by_campaign",
    ),

    # Field Rep Gmail login + share (kept)
    path("fieldrep-gmail-login/", views.fieldrep_gmail_login, name="fieldrep_gmail_login"),
    path("fieldrep-gmail-share-collateral/", views.fieldrep_gmail_share_collateral, name="fieldrep_gmail_share_collateral"),
    path(
        "fieldrep-gmail-share-collateral/<str:brand_campaign_id>/",
        views.fieldrep_gmail_share_collateral,
        name="fieldrep_gmail_share_collateral_by_campaign",
    ),

    # Field Rep Email Registration (kept)
    path("fieldrep-register/", views.fieldrep_email_registration, name="fieldrep_email_registration"),
    path("fieldrep-create-password/", views.fieldrep_create_password, name="fieldrep_create_password"),

    # Field Rep Dashboard
    path("dashboard/", views.fieldrep_dashboard, name="fieldrep_dashboard"),
    path("dashboard/campaign/<int:campaign_id>/", views.fieldrep_campaign_detail, name="fieldrep_campaign_detail"),
    path("dashboard/doctors/", views.doctor_list, name="doctor_list"),
    path("dashboard/campaign/<int:campaign_id>/doctors/", views.doctor_list, name="campaign_doctor_list"),
    path("dashboard/collateral/<int:pk>/delete/", views.dashboard_delete_collateral, name="dashboard_delete_collateral"),

    # Calendar / misc (kept)
    path("collaterals/edit/<int:pk>/", views.edit_collateral_dates, name="edit_collateral_dates"),
    path("edit-calendar/", views.edit_campaign_calendar, name="edit_campaign_calendar"),
    path("video-tracking/", views.video_tracking, name="video_tracking"),
    path("debug-collaterals/", views.debug_collaterals, name="debug_collaterals"),
]
