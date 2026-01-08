from django.urls import path
from . import views
from .views import (
    CollateralListView, CollateralDetailView,
    CollateralCreateView, CollateralUpdateView,
    CollateralDeleteView, link_collateral_to_campaign,
    unlink_collateral_from_campaign,
)
from .views_collateral_message import (
    collateral_message_list, collateral_message_create, collateral_message_edit,
    collateral_message_delete, get_collaterals_by_campaign, get_collateral_message
)

urlpatterns = [
    # NEW: add‑collateral route – keep this first
    path("add/", views.add_collateral_with_campaign, name="collaterals_add"),
    path("add/<str:brand_campaign_id>/", views.add_collateral_with_campaign, name="collaterals_add_branded"),

    # standard CRUD
    path("",                CollateralListView.as_view(),  name="collateral_list"),
    path("<int:pk>/",       CollateralDetailView.as_view(), name="collateral_detail"),
    path("create/",                   CollateralCreateView.as_view(), name="collateral_create"),
    path("<int:pk>/edit/",            CollateralUpdateView.as_view(), name="collateral_update"),
    path("<int:pk>/delete/",          CollateralDeleteView.as_view(), name="collateral_delete"),
    path('<int:pk>/replace/',          views.replace_collateral,      name='replace_collateral'),
    path('<int:pk>/dashboard-delete/', views.dashboard_delete_collateral, name='dashboard_delete_collateral'),
    # Support both /collaterals/<pk>/preview/ and /collaterals/<pk>/preview/<extra_id>/
    path('<int:pk>/preview/', views.preview_collateral, name='collateral_preview'),
    

    # bridging table helpers
    path("link/",           link_collateral_to_campaign,    name="link_collateral_to_campaign"),
    path("unlink/<int:pk>/",unlink_collateral_from_campaign,name="unlink_collateral"),
    path('calendar/edit/<int:pk>/', views.edit_campaign_collateral_dates, name='edit_campaign_calendar'),
    
    # collateral message management
    path("collateral-messages/", collateral_message_list, name="collateral_message_list"),
    path("collateral-messages/create/", collateral_message_create, name="collateral_message_create"),
    path("collateral-messages/<int:pk>/edit/", collateral_message_edit, name="collateral_message_edit"),
    path("collateral-messages/<int:pk>/delete/", collateral_message_delete, name="collateral_message_delete"),
    path("collateral-messages/get-collaterals/", get_collaterals_by_campaign, name="get_collaterals_by_campaign"),
    path("collateral-messages/get-message/", get_collateral_message, name="get_collateral_message"),
]
