from rest_framework import serializers
from campaign_management.models import Campaign
from collateral_management.models import Collateral
from shortlink_management.models import ShortLink
from sharing_management.models import ShareLog
from doctor_viewer.models import DoctorEngagement

class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Campaign
        fields = '__all__'

class CollateralSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Collateral
        fields = '__all__'

class ShortLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ShortLink
        fields = '__all__'

class ShareLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ShareLog
        fields = '__all__'

class DoctorEngagementSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DoctorEngagement
        fields = '__all__'