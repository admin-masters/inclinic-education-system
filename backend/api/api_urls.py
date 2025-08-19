from rest_framework.routers import DefaultRouter
from django.urls import path
from .api_views import (
    CampaignViewSet, CollateralViewSet, ShortLinkViewSet,
    ShareLogViewSet, DoctorEngagementViewSet, get_collateral_campaign
)

router = DefaultRouter()
router.register('campaigns',        CampaignViewSet,        basename='campaign')
router.register('collaterals',      CollateralViewSet,      basename='collateral')
router.register('shortlinks',       ShortLinkViewSet,       basename='shortlink')
router.register('shares',           ShareLogViewSet,        basename='sharelog')
router.register('engagements',      DoctorEngagementViewSet,basename='engagement')

urlpatterns = [
    path('get-collateral-campaign/<int:collateral_id>/', get_collateral_campaign, name='get_collateral_campaign'),
] + router.urls