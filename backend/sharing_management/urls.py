from django.urls import path
from . import views

urlpatterns = [
    path("", views.share_content, name="share_content"),
    path("success/", views.share_success, name="share_success"),
    path("logs/", views.list_share_logs, name="list_share_logs"),
    path("logs/<int:log_id>/", views.list_share_logs, name="share_log_detail"),

    path("dashboard/", views.fieldrep_dashboard, name="fieldrep_dashboard"),
    path("campaign/<str:campaign_id>/", views.fieldrep_campaign_detail, name="fieldrep_campaign_detail"),

    path("bulk-manual-upload/", views.bulk_manual_upload, name="bulk_manual_upload"),
    path("get-campaign-list/", views.get_campaign_list, name="get_campaign_list"),
    path("get-collaterals-by-campaign/", views.get_collaterals_by_campaign, name="get_collaterals_by_campaign"),
    path("get-videos-for-selected/", views.get_videos_for_selected, name="get_videos_for_selected"),

    path("doctor-view-log/", views.doctor_view_log, name="doctor_view_log"),
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),

    # Field rep auth (MASTER-backed)
    path("fieldrep-login/", views.fieldrep_login, name="fieldrep_login"),
    path("fieldrep-whatsapp-login/", views.fieldrep_whatsapp_login, name="fieldrep_whatsapp_login"),
    path("fieldrep-gmail-login/", views.fieldrep_gmail_login, name="fieldrep_gmail_login"),
    path("fieldrep-logout/", views.fieldrep_logout, name="fieldrep_logout"),

    path("fieldrep-forgot-password/", views.fieldrep_forgot_password, name="fieldrep_forgot_password"),
    path("fieldrep-reset-password/", views.fieldrep_reset_password, name="fieldrep_reset_password"),
    path("fieldrep-create-password/<int:field_rep_id>/", views.fieldrep_create_password, name="fieldrep_create_password"),

    # Prefilled flows (keep the routes, but point them to the updated handlers you actually have)
    path("prefilled-fieldrep-registration/", views.prefilled_fieldrep_registration, name="prefilled_fieldrep_registration"),
    path("prefilled-fieldrep-whatsapp-login/", views.prefilled_fieldrep_whatsapp_login, name="prefilled_fieldrep_whatsapp_login"),
    path("prefilled-fieldrep-gmail-login/", views.prefilled_fieldrep_gmail_login, name="prefilled_fieldrep_gmail_login"),

    # Use *_updated versions (your codebase already has these names)
    path("prefilled-fieldrep-whatsapp-share-collateral/", views.prefilled_fieldrep_whatsapp_share_collateral_updated, name="prefilled_fieldrep_whatsapp_share_collateral"),
    path("prefilled-fieldrep-gmail-share-collateral/", views.prefilled_fieldrep_gmail_share_collateral_updated, name="prefilled_fieldrep_gmail_share_collateral"),

    path("prefilled-doctor-list/<str:campaign_id>/", views.prefilled_doctor_list_by_campaign, name="prefilled_doctor_list_by_campaign"),
    path("doctor-list/<str:campaign_id>/", views.doctor_list_by_campaign, name="doctor_list_by_campaign"),

    path("set-campaign-session/", views.set_campaign_in_session, name="set_campaign_in_session"),
    path("save-doctor/", views.save_doctor, name="save_doctor"),
    path("delete-doctor/", views.delete_doctor, name="delete_doctor"),
    path("add-doctor/", views.add_doctor, name="add_doctor"),
    path("get-doctor-details/<int:doctor_id>/", views.get_doctor_details, name="get_doctor_details"),
    path("update-doctor/<int:doctor_id>/", views.update_doctor, name="update_doctor"),
    path("add-doctor-to-master/", views.add_doctor_to_master, name="add_doctor_to_master"),
    path("clear-doctor-list/", views.clear_doctor_list, name="clear_doctor_list"),

    path("share-collateral/<str:campaign_id>/", views.share_collateral_by_campaign, name="share_collateral_by_campaign"),
    path("dashboard/delete-collateral/<int:campaign_collateral_id>/", views.dashboard_delete_collateral, name="dashboard_delete_collateral"),
]
