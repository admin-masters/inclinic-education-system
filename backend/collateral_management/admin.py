# collateral_management/admin.py

from django.contrib import admin
from .models import Collateral, CampaignCollateral, CollateralMessage

@admin.register(Collateral)
class CollateralAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'is_active', 'upload_date', 'created_by')
    list_filter = ('type', 'is_active')
    search_fields = ('title', 'content_id')

@admin.register(CampaignCollateral)
class CampaignCollateralAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'collateral', 'start_date', 'end_date')

    # Avoid searching on fields that may be UUID typed but stored as varchar.
    # Searching by campaign name/title is safe.
    search_fields = (
        'campaign__name',
        'collateral__title',
    )

    # Disable problematic list filters that can trigger UUID parsing.
    list_filter = ()

@admin.register(CollateralMessage)
class CollateralMessageAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'collateral', 'is_active', 'created_at')
    list_filter = ('is_active', 'campaign__brand_campaign_id')
    search_fields = ('campaign__brand_campaign_id', 'collateral__title', 'message')
    list_editable = ('is_active',)
    ordering = ['-created_at']
    
    fieldsets = (
        ('Campaign & Collateral', {
            'fields': ('campaign', 'collateral')
        }),
        ('Message Content', {
            'fields': ('message', 'is_active')
        }),
    )
