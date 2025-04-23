# shortlink_management/urls.py

from django.urls import path
from .views import (
    ShortLinkListView,
    ShortLinkDetailView,
    create_short_link,
    ShortLinkDeleteView,
    resolve_shortlink
)

urlpatterns = [
    path('', ShortLinkListView.as_view(), name='shortlink_list'),
    path('<int:pk>/', ShortLinkDetailView.as_view(), name='shortlink_detail'),
    path('create/', create_short_link, name='shortlink_create'),
    path('<int:pk>/delete/', ShortLinkDeleteView.as_view(), name='shortlink_delete'),

    # Public-facing short code resolution
    path('go/<str:code>/', resolve_shortlink, name='resolve_shortlink'),
]