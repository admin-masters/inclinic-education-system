from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    CampaignSerializer, CollateralSerializer, ShortLinkSerializer,
    ShareLogSerializer, DoctorEngagementSerializer
)
from campaign_management.models  import Campaign
from collateral_management.models import Collateral
from shortlink_management.models import ShortLink
from sharing_management.models    import ShareLog
from doctor_viewer.models         import DoctorEngagement

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_collateral_campaign(request, collateral_id):
    """
    Get the brand campaign ID for a selected collateral
    """
    try:
        from campaign_management.models import CampaignCollateral
        from collateral_management.models import Collateral
        
        # First try to get from CampaignCollateral relationship
        campaign_collateral = CampaignCollateral.objects.select_related('campaign').filter(collateral_id=collateral_id).first()
        
        if campaign_collateral:
            return Response({
                'success': True,
                'brand_campaign_id': campaign_collateral.campaign.brand_campaign_id
            })
        
        # If not found in CampaignCollateral, check direct campaign relationship
        collateral = Collateral.objects.select_related('campaign').filter(id=collateral_id).first()
        if collateral and collateral.campaign:
            return Response({
                'success': True,
                'brand_campaign_id': collateral.campaign.brand_campaign_id
            })
        
        return Response({
            'success': False,
            'error': 'No campaign found for this collateral'
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        })

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