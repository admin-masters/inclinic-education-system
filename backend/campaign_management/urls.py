# campaign_management/urls.py
from django.urls import path
from . import views
from .views import (
    CampaignListView, CampaignDetailView, CampaignCreateView,
    CampaignUpdateView, CampaignDeleteView
)

urlpatterns = [
    path("", CampaignListView.as_view(), name="campaign_list"),

    # Publisher entry
    path("publisher-landing-page/", views.publisher_landing_page, name="publisher_landing_page"),
    path("publisher/select-campaign/", views.publisher_campaign_select, name="publisher_campaign_select"),

    # ✅ Canonical edit/view using CAMPAIGN-ID (brand_campaign_id)
    # Use <str:...> so template reversing never tries uuid.UUID(...)
    path("campaign/<str:campaign_id>/edit/", CampaignUpdateView.as_view(), name="campaign_by_id_update"),
    path("campaign/<str:campaign_id>/", views.CampaignDetailByCampaignIdView.as_view(), name="campaign_by_id_detail"),

    # Optional alias (keep existing publisher naming)
    path("publisher/<str:campaign_id>/edit/", CampaignUpdateView.as_view(), name="publisher_campaign_update"),

    # Legacy PK routes (keep if still used internally)
    path("<int:pk>/", CampaignDetailView.as_view(), name="campaign_detail"),
    path("create/", CampaignCreateView.as_view(), name="campaign_create"),
    path("<int:pk>/edit/", CampaignUpdateView.as_view(), name="campaign_update"),
    path("<int:pk>/delete/", CampaignDeleteView.as_view(), name="campaign_delete"),

    path("manage-data/", views.manage_data_panel, name="manage_data_panel"),

    # ✅ NEW: Thank-you page
    path("thank-you/", views.campaign_thank_you, name="campaign_thank_you"),
]
