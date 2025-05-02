from django.urls import path
from .views import resolve_view, log_engagement

urlpatterns = [
    path('log/',        log_engagement, name='doctor_view_log'),
    path('<str:code>/', resolve_view,    name='doctor_view'),
]