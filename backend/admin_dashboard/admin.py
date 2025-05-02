from django.contrib import admin
from .models import FieldRepCampaign

@admin.register(FieldRepCampaign)
class FieldRepCampaignAdmin(admin.ModelAdmin):
    list_display  = ('field_rep', 'campaign', 'assigned_at')
    list_filter   = ('campaign',)
    search_fields = ('field_rep__username', 'campaign__name')