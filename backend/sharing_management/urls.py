from django.urls import path
from .views import (
    share_content, share_success, list_share_logs,
    fieldrep_dashboard, fieldrep_campaign_detail,
    bulk_manual_upload, bulk_template_csv,
    bulk_pre_mapped_upload, bulk_pre_mapped_template,
    bulk_pre_filled_share_whatsapp, bulk_prefilled_whatsapp_template_csv, edit_campaign_calendar,
    dashboard_delete_collateral,
    prefilled_fieldrep_whatsapp_share_collateral  # Keep this if it's used elsewhere
)
from .views import bulk_manual_upload_whatsapp, bulk_whatsapp_template_csv
from . import views

urlpatterns = [
    path('share/', share_content, name='share_content'),
    path('prefilled-whatsapp-share-collateral/', prefilled_fieldrep_whatsapp_share_collateral, name='prefilled_fieldrep_whatsapp_share_collateral'),
    path('share/success/<int:share_log_id>/', share_success, name='share_success'),
    path('logs/', list_share_logs, name='share_logs'),

    # Field Rep Login
    path('fieldrep-login/', views.fieldrep_login, name='fieldrep_login'),
    path('fieldrep-forgot-password/', views.fieldrep_forgot_password, name='fieldrep_forgot_password'),
    path('fieldrep-reset-password/', views.fieldrep_reset_password, name='fieldrep_reset_password'),

    # Share Collateral Form
    path('fieldrep-share-collateral/', views.fieldrep_share_collateral, name='fieldrep_share_collateral'),
    path('fieldrep-share-collateral/<str:brand_campaign_id>/', views.fieldrep_share_collateral, name='fieldrep_share_collateral_by_campaign'),

    # Pre-filled Doctors Registration
    path('prefilled-fieldrep-register/', views.prefilled_fieldrep_registration, name='prefilled_fieldrep_registration'),
    path('prefilled-fieldrep-create-password/', views.prefilled_fieldrep_create_password, name='prefilled_fieldrep_create_password'),
    path('prefilled-fieldrep-share-collateral/', views.prefilled_fieldrep_share_collateral, name='prefilled_fieldrep_share_collateral'),
    path('prefilled-fieldrep-gmail-login/', views.prefilled_fieldrep_gmail_login, name='prefilled_fieldrep_gmail_login'),
    path('prefilled-fieldrep-gmail-share-collateral/', views.prefilled_fieldrep_gmail_share_collateral_updated, name='prefilled_fieldrep_gmail_share_collateral'),
    path('prefilled-fieldrep-whatsapp-login/<str:brand_campaign_id>/', views.prefilled_fieldrep_whatsapp_login, name='prefilled_fieldrep_whatsapp_login_campaign'),
    path('prefilled-fieldrep-whatsapp-login/', views.prefilled_fieldrep_whatsapp_login, name='prefilled_fieldrep_whatsapp_login'),
    path('prefilled-fieldrep-whatsapp-share-collateral/<str:brand_campaign_id>/', views.prefilled_fieldrep_whatsapp_share_collateral, name='prefilled_fieldrep_whatsapp_share_collateral_by_campaign'),
    path('prefilled-fieldrep-whatsapp-share-collateral/', views.prefilled_fieldrep_whatsapp_share_collateral, name='prefilled_fieldrep_whatsapp_share_collateral'),
    path('fieldrep-whatsapp-login/', views.fieldrep_whatsapp_login, name='fieldrep_whatsapp_login'),
    path('fieldrep-whatsapp-share-collateral/', views.fieldrep_whatsapp_share_collateral_updated, name='fieldrep_whatsapp_share_collateral'),

    # Field Rep Gmail Login
    path('fieldrep-gmail-login/', views.fieldrep_gmail_login, name='fieldrep_gmail_login'),
    path('fieldrep-gmail-share-collateral/', views.fieldrep_gmail_share_collateral, name='fieldrep_gmail_share_collateral'),
    path('fieldrep-gmail-share-collateral/<str:brand_campaign_id>/', views.fieldrep_gmail_share_collateral, name='fieldrep_gmail_share_collateral_by_campaign'),

    # WhatsApp Sharing
    path('whatsapp-share/', prefilled_fieldrep_whatsapp_share_collateral, name='whatsapp_share_collateral'),
    
    # Field Rep Dashboard
    path('dashboard/', fieldrep_dashboard, name='fieldrep_dashboard'),
    path('dashboard/campaign/<int:campaign_id>/', fieldrep_campaign_detail, name='fieldrep_campaign_detail'),
    path('dashboard/doctors/', views.doctor_list, name='doctor_list'),
    path('dashboard/campaign/<int:campaign_id>/doctors/', views.doctor_list, name='campaign_doctor_list'),

    # Field Rep Email Registration
    path('fieldrep-register/', views.fieldrep_email_registration, name='fieldrep_email_registration'),
    path('fieldrep-create-password/', views.fieldrep_create_password, name='fieldrep_create_password'),

    # Admin Tools
    path("bulk-manual-share/", bulk_manual_upload, name="bulk_manual_upload"),
    path("bulk-manual-template.csv", bulk_template_csv, name="bulk_manual_template"),
    path("bulk-upload-success/", views.bulk_upload_success, name="bulk_upload_success"),
    path("bulk-upload-help/", views.bulk_upload_help, name="bulk_upload_help"),
    path("all-share-logs/", views.all_share_logs, name="all_share_logs"),

    # Pre-mapped upload
    path("bulk/premapped/", bulk_pre_mapped_upload, name="bulk_pre_mapped_upload"),
    path("bulk/premapped/template/", bulk_pre_mapped_template, name="bulk_pre_mapped_template"),
    
    # Pre-mapped by login
    path(
        "bulk/premapped-by-login/",
        views.bulk_pre_mapped_by_login,
        name="bulk_pre_mapped_by_login",
    ),
    path(
        "bulk/premapped-by-login/template.csv",
        views.bulk_pre_mapped_by_login_template,
        name="bulk_pre_mapped_by_login_template",
    ),

    path(
        "bulk-manual-share-whatsapp/",
        bulk_manual_upload_whatsapp,
        name="bulk_manual_upload_whatsapp",
    ),
    path(
        "bulk-manual-share-whatsapp-template.csv",
        bulk_whatsapp_template_csv,
        name="bulk_manual_whatsapp_template",
    ),
    path(
    "bulk-prefilled-whatsapp/",
    bulk_pre_filled_share_whatsapp,
    name="bulk_pre_filled_share_whatsapp",
),
path(
    "bulk-prefilled-whatsapp-template.csv",
    bulk_prefilled_whatsapp_template_csv,
    name="bulk_prefilled_whatsapp_template",
),
path('collaterals/edit/<int:pk>/', views.edit_collateral_dates, name='edit_collateral_dates'),
path('edit-calendar/', edit_campaign_calendar, name='edit_campaign_calendar'),
path('video-tracking/', views.video_tracking, name='video_tracking'),
path('debug-collaterals/', views.debug_collaterals, name='debug_collaterals'),
    path('dashboard/collateral/<int:pk>/delete/', dashboard_delete_collateral, name='dashboard_delete_collateral'),

]
