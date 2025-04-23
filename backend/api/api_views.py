from rest_framework import viewsets, permissions
from .serializers import (
    CampaignSerializer, CollateralSerializer, ShortLinkSerializer,
    ShareLogSerializer, DoctorEngagementSerializer
)
from campaign_management.models  import Campaign
from collateral_management.models import Collateral
from shortlink_management.models import ShortLink
from sharing_management.models    import ShareLog
from doctor_viewer.models         import DoctorEngagement

class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'

class CampaignViewSet(viewsets.ModelViewSet):
    queryset           = Campaign.objects.all()
    serializer_class   = CampaignSerializer
    permission_classes = [IsAdmin]

class CollateralViewSet(viewsets.ModelViewSet):
    queryset           = Collateral.objects.all()
    serializer_class   = CollateralSerializer
    permission_classes = [IsAdmin]

class ShortLinkViewSet(viewsets.ModelViewSet):
    queryset           = ShortLink.objects.all()
    serializer_class   = ShortLinkSerializer
    permission_classes = [IsAdmin]

class ShareLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = ShareLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # field rep sees only their shares; admin sees all
        if self.request.user.role == 'field_rep':
            return ShareLog.objects.filter(field_rep=self.request.user)
        return ShareLog.objects.all()

class DoctorEngagementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = DoctorEngagementSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset           = DoctorEngagement.objects.all()