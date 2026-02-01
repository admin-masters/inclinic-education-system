# doctor_viewer/urls.py
from django.urls import path
from .views import resolve_view, log_engagement, doctor_report, doctor_collateral_verify, doctor_collateral_view, tracking_dashboard

urlpatterns = [
    path('tracking-dashboard/', tracking_dashboard, name='tracking_dashboard'),
    path('log/', log_engagement, name='doctor_view_log'),
    path('report/<str:code>/', doctor_report, name='doctor_view_report'),
    path('collateral/verify/', doctor_collateral_verify, name='doctor_collateral_verify'),
    path('collateral/view/', doctor_collateral_view, name='doctor_collateral_view'),
    path('<str:code>/', resolve_view, name='doctor_view'),
]