# collateral_management/admin.py

from django.contrib import admin
from .models import Collateral, CampaignCollateral

@admin.register(Collateral)
class CollateralAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'is_active', 'upload_date', 'created_by')
    list_filter = ('type', 'is_active')
    search_fields = ('title', 'content_id')

@admin.register(CampaignCollateral)
class CampaignCollateralAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'collateral', 'start_date', 'end_date')
    search_fields = ('campaign__name', 'collateral__title')