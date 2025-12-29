from django.urls import path
from . import views
from .views import (
    CollateralListView, CollateralDetailView,
    CollateralCreateView, CollateralUpdateView,
    CollateralDeleteView, link_collateral_to_campaign,
    unlink_collateral_from_campaign,
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
]
