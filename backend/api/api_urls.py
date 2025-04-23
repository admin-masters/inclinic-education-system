from rest_framework.routers import DefaultRouter
from .api_views import (
    CampaignViewSet, CollateralViewSet, ShortLinkViewSet,
    ShareLogViewSet, DoctorEngagementViewSet
)

router = DefaultRouter()
router.register('campaigns',        CampaignViewSet,        basename='campaign')
router.register('collaterals',      CollateralViewSet,      basename='collateral')
router.register('shortlinks',       ShortLinkViewSet,       basename='shortlink')
router.register('shares',           ShareLogViewSet,        basename='sharelog')
router.register('engagements',      DoctorEngagementViewSet,basename='engagement')

urlpatterns = router.urls