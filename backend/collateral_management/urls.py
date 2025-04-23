# collateral_management/urls.py

from django.urls import path
from .views import (
    CollateralListView, CollateralDetailView,
    CollateralCreateView, CollateralUpdateView,
    CollateralDeleteView, link_collateral_to_campaign,
    unlink_collateral_from_campaign
)

urlpatterns = [
    path('', CollateralListView.as_view(), name='collateral_list'),
    path('<int:pk>/', CollateralDetailView.as_view(), name='collateral_detail'),
    path('create/', CollateralCreateView.as_view(), name='collateral_create'),
    path('<int:pk>/edit/', CollateralUpdateView.as_view(), name='collateral_update'),
    path('<int:pk>/delete/', CollateralDeleteView.as_view(), name='collateral_delete'),

    # bridging table link/unlink
    path('link/', link_collateral_to_campaign, name='link_collateral_to_campaign'),
    path('unlink/<int:pk>/', unlink_collateral_from_campaign, name='unlink_collateral'),
]