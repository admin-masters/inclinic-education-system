from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    CampaignViewSet, 
    CampaignContentViewSet, 
    DoctorShareViewSet,
    doctor_content_view,
    check_auth
)

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet)
router.register(r'contents', CampaignContentViewSet)
router.register(r'shares', DoctorShareViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/check/', check_auth, name='check_auth'),
    path('doctor/content/<int:share_id>/', doctor_content_view, name='doctor_content_view'),
] 