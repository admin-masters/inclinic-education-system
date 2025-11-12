from django.contrib import admin
from user_management.models import User
from .models import Campaign, CampaignAssignment

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand_name', 'company_name', 'status', 'start_date', 'end_date', 'created_by')
    list_filter = ('status', 'brand_name')
    search_fields = ('name', 'brand_name')
    date_hierarchy = 'start_date'

class CampaignAssignmentInline(admin.TabularInline):
    model = CampaignAssignment
    extra = 1
    autocomplete_fields = ['field_rep']

@admin.register(CampaignAssignment)
class CampaignAssignmentAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'field_rep', 'assigned_on')
    search_fields = ('campaign__name', 'field_rep__username')
    list_filter = ('campaign',)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'field_rep':
            # Get the campaign_id from the URL or form data
            campaign_id = None
            if hasattr(request, 'resolver_match') and request.resolver_match:
                campaign_id = request.resolver_match.kwargs.get('object_id')
            campaign_id = campaign_id or request.POST.get('campaign')
            
            if campaign_id:
                # Get field reps already assigned to this campaign
                assigned_reps = CampaignAssignment.objects.filter(
                    campaign_id=campaign_id
                ).values_list('field_rep_id', flat=True)
                # Filter to show only field reps not already assigned to this campaign
                kwargs['queryset'] = User.objects.filter(
                    role='field_rep',
                    is_active=True
                ).exclude(id__in=assigned_reps)
            else:
                # If no campaign selected yet, only show field reps
                kwargs['queryset'] = User.objects.filter(role='field_rep', is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)