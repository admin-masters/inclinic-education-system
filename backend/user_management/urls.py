# user_management/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.user_profile, name='user_profile'),
    
    # Add more if you want to handle custom user flows
]