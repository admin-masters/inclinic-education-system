from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('',              views.dashboard,              name='dashboard'),
    path('bulk-fieldreps/', views.bulk_upload_fieldreps, name='bulk_upload'),

    
]