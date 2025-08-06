# campaign_management/forms.py

from django import forms
from .models import Campaign, CampaignAssignment, CampaignCollateral
from user_management.models import User  # your custom User model

# Campaign Creation Form
class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ['name', 'brand_name', 'start_date', 'end_date', 'description', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'brand_name': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


# Field Rep Assignment Form
class CampaignAssignmentForm(forms.ModelForm):
    field_rep = forms.ModelChoiceField(
        queryset=User.objects.filter(role='field_rep', active=True),
        label="Select Field Rep",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = CampaignAssignment
        fields = ['campaign', 'field_rep']
        widgets = {
            'campaign': forms.Select(attrs={'class': 'form-select'}),
        }


# ✅ NEWLY ADDED: Collateral Assignment Form
class CampaignCollateralForm(forms.ModelForm):
    class Meta:
        model = CampaignCollateral
        fields = ['collateral', 'start_date', 'end_date']
        widgets = {
            'collateral': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
