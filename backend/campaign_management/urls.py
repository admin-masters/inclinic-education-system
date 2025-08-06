# campaign_management/urls.py

from django.urls import path
from .views import *
#  (
#     CampaignListView, CampaignDetailView, CampaignCreateView,
#     CampaignUpdateView, CampaignDeleteView, assign_field_reps, remove_field_rep
# )
from . import views
urlpatterns = [
    path('', CampaignListView.as_view(), name='campaign_list'),
    path('<int:pk>/', CampaignDetailView.as_view(), name='campaign_detail'),
    path('create/', CampaignCreateView.as_view(), name='campaign_create'),
    path('<int:pk>/edit/', CampaignUpdateView.as_view(), name='campaign_update'),
    path('<int:pk>/delete/', CampaignDeleteView.as_view(), name='campaign_delete'),

    # Field Rep assignment
    path('<int:pk>/assign/', assign_field_reps, name='assign_field_reps'),
    path('<int:pk>/unassign/<int:assignment_id>/', remove_field_rep, name='remove_field_rep'),
    path('collaterals/edit/<int:pk>/', views.edit_collateral_dates, name='edit_collateral_dates'),
]