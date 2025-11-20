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
    Get the brand campaign ID, start date, and end date for a selected collateral.
    Prefer dates from the bridging table in collateral_management (DateTime fields),
    falling back to campaign_management (Date fields), and finally direct collateral → campaign.
    """
    try:
        from collateral_management.models import CampaignCollateral as CMBridge, Collateral
        from campaign_management.models import CampaignCollateral as CMCampaign

        # 1) Prefer bridging record from collateral_management
        bridge = CMBridge.objects.select_related('campaign').filter(collateral_id=collateral_id).order_by('-updated_at').first()
        if bridge:
            return Response({
                'success': True,
                'brand_campaign_id': bridge.campaign.brand_campaign_id,
                'start_date': bridge.start_date.strftime('%Y-%m-%d') if bridge.start_date else '',
                'end_date': bridge.end_date.strftime('%Y-%m-%d') if bridge.end_date else ''
            })

        # 2) Fall back to campaign_management CampaignCollateral
        cm_cc = CMCampaign.objects.select_related('campaign').filter(collateral_id=collateral_id).first()
        if cm_cc:
            return Response({
                'success': True,
                'brand_campaign_id': cm_cc.campaign.brand_campaign_id,
                'start_date': cm_cc.start_date.strftime('%Y-%m-%d') if cm_cc.start_date else '',
                'end_date': cm_cc.end_date.strftime('%Y-%m-%d') if cm_cc.end_date else ''
            })

        # 3) Finally, use direct collateral → campaign relationship
        collateral = Collateral.objects.select_related('campaign').filter(id=collateral_id).first()
        if collateral and collateral.campaign:
            return Response({
                'success': True,
                'brand_campaign_id': collateral.campaign.brand_campaign_id,
                'start_date': '',
                'end_date': ''
            })

        return Response({'success': False, 'error': 'No campaign found for this collateral'})
    except Exception as e:
        return Response({'success': False, 'error': str(e)})

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