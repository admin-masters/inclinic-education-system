from django.urls import path
from .views import (
    share_content, share_success, list_share_logs,
    fieldrep_dashboard, fieldrep_campaign_detail
)

urlpatterns = [
    path('share/', share_content, name='share_content'),
    path('share/success/<int:share_log_id>/<path:wa_link>/', share_success, name='share_success'),
    path('logs/', list_share_logs, name='share_logs'),
    
    # Field Rep Dashboard
    path('dashboard/', fieldrep_dashboard, name='fieldrep_dashboard'),
    path('dashboard/campaign/<int:campaign_id>/', fieldrep_campaign_detail, name='fieldrep_campaign_detail'),
]
