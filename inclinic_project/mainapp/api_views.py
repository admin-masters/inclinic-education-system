from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from .models import Campaign, CampaignContent, DoctorShare
from .serializers import (
    CampaignSerializer, 
    CampaignContentSerializer, 
    DoctorShareSerializer
)

class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.filter(status='ACTIVE')
    serializer_class = CampaignSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class CampaignContentViewSet(viewsets.ModelViewSet):
    queryset = CampaignContent.objects.all()
    serializer_class = CampaignContentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        campaign_id = self.request.query_params.get('campaign_id')
        if campaign_id:
            return CampaignContent.objects.filter(campaign_id=campaign_id)
        return super().get_queryset()

class DoctorShareViewSet(viewsets.ModelViewSet):
    queryset = DoctorShare.objects.all()
    serializer_class = DoctorShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return DoctorShare.objects.filter(rep=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(rep=self.request.user)

@api_view(['GET'])
def doctor_content_view(request, share_id):
    """Public endpoint for doctors to view shared content"""
    share = get_object_or_404(DoctorShare, id=share_id)
    # Increment view count
    share.view_count += 1
    share.save()
    
    serializer = DoctorShareSerializer(share)
    return Response(serializer.data)

@api_view(['GET'])
def check_auth(request):
    """Check if user is authenticated and return their info"""
    if request.user.is_authenticated:
        from .serializers import UserSerializer
        serializer = UserSerializer(request.user)
        return Response({
            'isAuthenticated': True,
            'user': serializer.data
        })
    return Response({'isAuthenticated': False}) 