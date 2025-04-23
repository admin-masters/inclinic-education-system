# campaign_management/forms.py

from django import forms
from .models import Campaign, CampaignAssignment
from user_management.models import User  # your custom User model

class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ['name', 'brand_name', 'start_date', 'end_date', 'description', 'status']


class CampaignAssignmentForm(forms.ModelForm):
    field_rep = forms.ModelChoiceField(
        queryset=User.objects.filter(role='field_rep', active=True),
        label="Select Field Rep"
    )

    class Meta:
        model = CampaignAssignment
        fields = ['campaign', 'field_rep']
        # We'll assign campaign automatically in the view, or we can keep it user-editable.