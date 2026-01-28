from django.urls import path
from .views import *

urlpatterns = [
    path('', CampaignListView.as_view(), name='campaign_list'),

    path("publisher-landing-page/", publisher_landing_page, name="publisher_landing_page"),
    path("publisher/select-campaign/", publisher_campaign_select, name="publisher_campaign_select"),
    path("publisher/<str:campaign_id>/edit/", CampaignUpdateView.as_view(), name="publisher_campaign_update"),

    # Use <str:pk> for Detail/Update/Delete
    path('<str:pk>/', CampaignDetailView.as_view(), name='campaign_detail'),
    path('create/', CampaignCreateView.as_view(), name='campaign_create'),
    path('<str:pk>/edit/', CampaignUpdateView.as_view(), name='campaign_update'),
    path('<str:pk>/delete/', CampaignDeleteView.as_view(), name='campaign_delete'),

    # Field Rep assignment stays int because it's a local DB PK
    path('<int:pk>/assign/', assign_field_reps, name='assign_field_reps'),
    path('<int:pk>/unassign/<int:assignment_id>/', remove_field_rep, name='remove_field_rep'),
    path('collaterals/edit/<int:pk>/', edit_collateral_dates, name='edit_collateral_dates'),

    path('manage-data/', manage_data_panel, name='manage_data_panel'),
]
