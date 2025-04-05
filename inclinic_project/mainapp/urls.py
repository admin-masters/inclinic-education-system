from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('oauth/', include('social_django.urls', namespace='social')),  # Google OAuth callbacks
    path('logged-in/', views.logged_in, name='logged_in'),
    path('create_campaign/', views.create_campaign, name='create_campaign'),
    path('list_campaigns/', views.list_campaigns, name='list_campaigns'),
    path('edit_campaign/<int:campaign_id>/', views.edit_campaign, name='edit_campaign'),
    path('archive_campaign/<int:campaign_id>/', views.archive_campaign, name='archive_campaign'),
    path('create_content/<int:campaign_id>/', views.create_content, name='create_content'),
    path('view_campaign_contents/<int:campaign_id>/', views.view_campaign_contents, name='view_campaign_contents'),
    path('share_collateral/<int:campaign_id>/', views.share_collateral, name='share_collateral'),
]

