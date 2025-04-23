# campaign_management/admin.py

from django.contrib import admin
from .models import Campaign, CampaignAssignment

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand_name', 'status', 'start_date', 'end_date', 'created_by')
    list_filter = ('status', 'brand_name')
    search_fields = ('name', 'brand_name')
    date_hierarchy = 'start_date'

@admin.register(CampaignAssignment)
class CampaignAssignmentAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'field_rep', 'assigned_on')
    search_fields = ('campaign__name', 'field_rep__username')