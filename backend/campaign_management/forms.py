# campaign_management/forms.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models
from django.db.models import Q
from datetime import datetime, time
from PIL import Image  # ensure Pillow is installed
import io
import os
import uuid
import re

from .models import Campaign, CampaignAssignment, CampaignCollateral
from user_management.models import User  # your custom User model

DATE_FMT = "%d/%m/%Y"  # dd/mm/yyyy
REQUIRED_PRINT_COLUMNS = {
    "Collateral Name",
    "Schedule Date of Collaterals",
    "Delivery Date of Collateral",
    "Delivery Address",
    "Contact Person Name",
    "Contact Person Phone Number",
}

from datetime import datetime, time
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from PIL import Image

from .models import Campaign

MAX_LOGO_SIZE_MB = 2
MAX_LOGO_SIZE_BYTES = MAX_LOGO_SIZE_MB * 1024 * 1024
MAX_LOGO_WIDTH = 500
MAX_LOGO_HEIGHT = 500

# Campaign Creation Form
class CampaignForm(forms.ModelForm):
    """
    Publisher-editable campaign details (PE system).

    Master-owned fields are intentionally NOT exposed:
      - incharge_name, incharge_contact, num_doctors, company_name, brand_name, brand_campaign_id, printing_excel
    """

    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=True)
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=True)

    printing_required = forms.ChoiceField(
        choices=[("yes", "Yes"), ("no", "No")],
        required=True,
        label="Does this campaign require printing of collateral by Inditech?",
    )

    class Meta:
        model = Campaign
        fields = [
            "name",
            "incharge_designation",
            "items_per_clinic_per_year",
            "start_date",
            "end_date",
            "contract",
            "brand_logo",
            "company_logo",
            "printing_required",
            "description",
            "status",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "incharge_designation": forms.TextInput(attrs={"class": "form-control"}),
            "items_per_clinic_per_year": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-fill date inputs from stored datetimes
        if self.instance and getattr(self.instance, "start_date", None):
            self.fields["start_date"].initial = self.instance.start_date.date()
        if self.instance and getattr(self.instance, "end_date", None):
            self.fields["end_date"].initial = self.instance.end_date.date()

        # Pre-fill printing_required choice
        if self.instance and getattr(self.instance, "printing_required", None) is True:
            self.fields["printing_required"].initial = "yes"
        elif self.instance and getattr(self.instance, "printing_required", None) is False:
            self.fields["printing_required"].initial = "no"

    def clean(self):
        data = super().clean()

        if not (data.get("name") or "").strip():
            self.add_error("name", "This field is required.")

        start_date_val = data.get("start_date")
        end_date_val = data.get("end_date")

        if start_date_val:
            data["start_date"] = self._parse_date(start_date_val)
        if end_date_val:
            data["end_date"] = self._parse_date_end(end_date_val)

        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            self.add_error("end_date", "End date cannot be earlier than start date.")

        pr = data.get("printing_required")
        if pr == "yes":
            data["printing_required"] = True
        elif pr == "no":
            data["printing_required"] = False
        elif not isinstance(pr, bool):
            self.add_error("printing_required", "Please select Yes or No.")

        brand_logo = data.get("brand_logo")
        if brand_logo:
            self._validate_logo(brand_logo)

        company_logo = data.get("company_logo")
        if company_logo:
            self._validate_logo(company_logo)

        return data

    def _parse_date(self, date_input):
        if isinstance(date_input, str):
            date_obj = datetime.strptime(date_input, "%Y-%m-%d").date()
        else:
            date_obj = date_input
        naive_dt = datetime.combine(date_obj, time.min)
        return timezone.make_aware(naive_dt)

    def _parse_date_end(self, date_input):
        if isinstance(date_input, str):
            date_obj = datetime.strptime(date_input, "%Y-%m-%d").date()
        else:
            date_obj = date_input
        naive_dt = datetime.combine(date_obj, time.max)
        return timezone.make_aware(naive_dt)

    def _validate_logo(self, logo_file):
        if logo_file.size > MAX_LOGO_SIZE_BYTES:
            raise ValidationError(f"Logo file must be less than {MAX_LOGO_SIZE_MB}MB.")

        try:
            img = Image.open(logo_file)
            width, height = img.size
        except Exception:
            raise ValidationError("Invalid image file.")

        if width > MAX_LOGO_WIDTH or height > MAX_LOGO_HEIGHT:
            raise ValidationError(f"Logo dimensions must be at most {MAX_LOGO_WIDTH}x{MAX_LOGO_HEIGHT}px.")


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

    def clean(self):
        cleaned_data = super().clean()
        campaign = cleaned_data.get('campaign')
        field_rep = cleaned_data.get('field_rep')

        if campaign and field_rep:
            # Check if this field rep is already assigned to this campaign
            existing_assignment = CampaignAssignment.objects.filter(
                campaign=campaign,
                field_rep=field_rep
            ).exists()
            
            if existing_assignment and (not self.instance or not self.instance.pk):
                raise ValidationError("This field rep is already assigned to the selected campaign.")

        return cleaned_data


from collateral_management.models import Collateral as CMCollateral
from collateral_management.models import CampaignCollateral as CMCampaignCollateral
# Collateral Assignment Form
class CampaignCollateralForm(forms.ModelForm):
    campaign = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'readonly': 'readonly',
            'style': 'background-color: #e9ecef; cursor: not-allowed;'
        }),
        label="Brand Campaign ID",
        disabled=True
    )
    collateral = forms.ModelChoiceField(
        queryset=CMCollateral.objects.none(),  # Will be set in __init__
        label="Select Collateral",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        # Use the bridging model from collateral_management to align with Collateral
        model = CMCampaignCollateral
        fields = ['collateral', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        brand_campaign_id = kwargs.pop('brand_campaign_id', None)
        super().__init__(*args, **kwargs)
        
        from django.db.models import Q
        from campaign_management.models import Campaign
        
        # Initialize an empty queryset
        collaterals = CMCollateral.objects.none()
        
        # Get the campaign if brand_campaign_id is provided
        campaign = None
        if brand_campaign_id:
            try:
                campaign = Campaign.objects.get(brand_campaign_id=brand_campaign_id)
                self.fields['campaign'].initial = campaign.brand_campaign_id
            except Campaign.DoesNotExist:
                pass
        
        # If we have an existing instance, get the campaign from it
        if self.instance and self.instance.pk:
            campaign = self.instance.campaign
            self.fields['campaign'].initial = campaign.brand_campaign_id
        
        # If we have a campaign, filter collaterals for that campaign
        if campaign:
            # Get collaterals from direct relationship (campaign field on Collateral)
            direct_collaterals = CMCollateral.objects.filter(campaign=campaign)
            
            # Get collaterals from many-to-many relationship (through CampaignCollateral)
            m2m_collaterals = CMCollateral.objects.filter(campaign_collaterals__campaign=campaign)
            
            # Combine both querysets
            collaterals = (direct_collaterals | m2m_collaterals).distinct()
            
            # If we're editing an existing instance, make sure to include the current collateral
            if self.instance and self.instance.pk:
                current_collateral = self.instance.collateral
                if current_collateral and not collaterals.filter(pk=current_collateral.pk).exists():
                    collaterals = collaterals | CMCollateral.objects.filter(pk=current_collateral.pk)
        else:
            # If no campaign is specified, show all collaterals
            collaterals = CMCollateral.objects.all()
        
        # Set the filtered queryset
        self.fields['collateral'].queryset = collaterals.order_by('title')
        
        # If we have an instance, set the initial value for the collateral field
        if self.instance and self.instance.pk and self.instance.collateral:
            self.fields['collateral'].initial = self.instance.collateral

    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        # Validate dates
        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date cannot be earlier than start date.")
            
        # Keep campaign field for new records, but validate it exists
        if 'campaign' in cleaned_data and cleaned_data['campaign']:
            # Validate that the campaign exists
            from campaign_management.models import Campaign
            try:
                Campaign.objects.get(brand_campaign_id=cleaned_data['campaign'])
            except Campaign.DoesNotExist:
                raise ValidationError(f"Campaign with Brand Campaign ID '{cleaned_data['campaign']}' not found.")
        elif not self.instance.pk:
            # For new records, campaign is required
            if 'campaign' not in cleaned_data or not cleaned_data.get('campaign'):
                raise ValidationError("Brand Campaign ID is required for new campaign collateral.")
            
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # For existing instances, preserve the original campaign
        if self.instance and self.instance.pk:
            original = CMCampaignCollateral.objects.get(pk=self.instance.pk)
            instance.campaign = original.campaign
        else:
            # For new instances, set campaign from the form data
            campaign_brand_id = self.cleaned_data.get('campaign')
            if campaign_brand_id:
                from campaign_management.models import Campaign
                try:
                    campaign = Campaign.objects.get(brand_campaign_id=campaign_brand_id)
                    instance.campaign = campaign
                except Campaign.DoesNotExist:
                    # This should have been caught in clean(), but handle gracefully
                    if commit:
                        raise ValidationError(f"Campaign with Brand Campaign ID '{campaign_brand_id}' not found.")

        # Normalize start/end into DateTime for the collateral_management.CampaignCollateral model
        # If date objects are provided (from <input type="date">), convert to start-of-day and end-of-day
        start_date_val = self.cleaned_data.get('start_date')
        end_date_val = self.cleaned_data.get('end_date')
        if start_date_val and not hasattr(start_date_val, 'hour'):
            instance.start_date = timezone.make_aware(datetime.combine(start_date_val, time.min))
        if end_date_val and not hasattr(end_date_val, 'hour'):
            # Use end of the day, drop microseconds for consistency
            instance.end_date = timezone.make_aware(datetime.combine(end_date_val, time.max.replace(microsecond=0)))
        
        if commit:
            instance.save()
        return instance


# Campaign Search Form
class CampaignSearchForm(forms.Form):
    brand_campaign_id = forms.CharField(
        required=False,
        label="Brand Campaign ID",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by Brand Campaign ID'})
    )
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by Campaign Name'})
    )
    brand_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by Brand Name'})
    )
    status = forms.ChoiceField(required=False, label="Status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Campaign
        # Try legacy constant first; otherwise read from the field
        choices = getattr(Campaign, "STATUS_CHOICES", None)
        if not choices:
            try:
                choices = Campaign._meta.get_field("status").choices
            except Exception:
                choices = ()
        self.fields["status"].choices = [("", "All Statuses")] + list(choices)


# Campaign Filter Form for Reports
class CampaignFilterForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        label="From Date",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        required=False,
        label="To Date",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    status = forms.ChoiceField(required=False, label="Status")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Campaign
        # Try legacy constant first; otherwise read from the field
        choices = getattr(Campaign, "STATUS_CHOICES", None)
        if not choices:
            try:
                choices = Campaign._meta.get_field("status").choices
            except Exception:
                choices = ()
        self.fields["status"].choices = [("", "All Statuses")] + list(choices)
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date cannot be earlier than start date.")
            
        return cleaned_data