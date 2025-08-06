from django.urls import path
from .views import resolve_view, log_engagement, doctor_report, doctor_collateral_verify, doctor_collateral_view


urlpatterns = [
    path('log/',        log_engagement, name='doctor_view_log'),
    path('<str:code>/', resolve_view,    name='doctor_view'),
    path('report/<str:code>/', doctor_report, name='doctor_view_report'),
    path('collateral/verify/', doctor_collateral_verify, name='doctor_collateral_verify'),
    path('collateral/view/', doctor_collateral_view, name='doctor_collateral_view'),
]