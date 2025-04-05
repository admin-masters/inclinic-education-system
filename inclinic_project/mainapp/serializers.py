from rest_framework import serializers
from .models import Campaign, CampaignContent, DoctorShare, Profile
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class CampaignSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    
    class Meta:
        model = Campaign
        fields = ['id', 'campaign_name', 'therapy_area', 'start_date', 
                 'end_date', 'status', 'created_by', 'created_at']

class CampaignContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignContent
        fields = ['id', 'campaign', 'content_type', 'content_title', 
                 'file_path', 'vimeo_url', 'created_at']

class DoctorShareSerializer(serializers.ModelSerializer):
    campaign = CampaignSerializer(read_only=True)
    content = CampaignContentSerializer(read_only=True)
    rep = UserSerializer(read_only=True)
    
    class Meta:
        model = DoctorShare
        fields = ['id', 'campaign', 'content', 'rep', 'doctor_phone', 
                 'share_date', 'view_count'] 