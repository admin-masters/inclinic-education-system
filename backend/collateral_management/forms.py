

# collateral_management/forms.py
from django import forms
from django.core.exceptions import ValidationError, FieldError
from .models import Collateral, CampaignCollateral, CollateralMessage
from campaign_management.models import Campaign

class CampaignCollateralDateForm(forms.ModelForm):
    class Meta:
        model = CampaignCollateral
        fields = ['start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
MAX_FILE_SIZE_MB = 2

class CollateralForm(forms.ModelForm):
    # Purpose choices moved to a dedicated field
    PURPOSE_CHOICES = [
        ('Doctor education short', 'Doctor education short'),
        ('Doctor education long', 'Doctor education long'),
        ('Patient education compliance', 'Patient education compliance'),
        ('Patient education general', 'Patient education general'),
    ]

    purpose = forms.ChoiceField(
        choices=[('', 'Select Purpose of the Collateral')] + PURPOSE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Purpose of the Collateral"
    )

    # Title is now a genuine text input again
    title = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Content Title"
    )

    # NEW fields
    doctor_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Doctor's Name (optional)"
    )
    webinar_title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Webinar Title"
    )
    webinar_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        label="Webinar Description"
    )
    webinar_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
        label="DIAP Webinar Link"
    )
    webinar_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Webinar Date"
    )

    banner_1    = forms.ImageField(required=False)
    banner_2    = forms.ImageField(required=False)
    description = forms.CharField(max_length=255, required=False)
    is_active   = forms.BooleanField(required=False, initial=True, widget=forms.HiddenInput())

    # Accept Vimeo embed code instead of direct URL
    vimeo_embed_code = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '<iframe src="https://player.vimeo.com/video/123456789" ...></iframe>'}),
        label="Vimeo Embed Code"
    )

    def __init__(self, *args, **kwargs):
        brand_campaign_id = kwargs.pop('brand_campaign_id', None)
        super().__init__(*args, **kwargs)

        # If brand_campaign_id is provided, filter the campaign choices
        if brand_campaign_id:
            self.fields['campaign'].queryset = Campaign.objects.filter(brand_campaign_id=brand_campaign_id)
            # If there's only one campaign, set it as the initial value
            if self.fields['campaign'].queryset.count() == 1:
                self.fields['campaign'].initial = self.fields['campaign'].queryset.first()
                # Optionally make it read-only
                self.fields['campaign'].widget.attrs['readonly'] = True
                self.fields['campaign'].widget.attrs['class'] = 'form-control-plaintext'
                self.fields['campaign'].help_text = 'This field is set based on the selected brand campaign.'

        # Hide the underlying vimeo_url field; we drive it from embed code
        if 'vimeo_url' in self.fields:
            self.fields['vimeo_url'].widget = forms.HiddenInput()

    class Meta:
        model  = Collateral
        fields = [
            'campaign', 'purpose', 'title', 'content_id', 'type',
            'file', 'vimeo_url',  # stored URL populated from embed code
            'banner_1', 'banner_2',
            'description', 'doctor_name',
            'webinar_title', 'webinar_description', 'webinar_url', 'webinar_date',
            'is_active'
        ]

    # ── custom validation ───────────────────────────────────────────────────
    def clean(self):
        cleaned = super().clean()
        c_type = cleaned.get('type')
        file_f = cleaned.get('file')
        url_f  = cleaned.get('vimeo_url')
        embed  = cleaned.get('vimeo_embed_code', '').strip()

        # If embed code is provided, extract Vimeo video ID or src
        if embed:
            import re
            # Try to extract src from iframe
            src_match = re.search(r'src\s*=\s*"([^"]+)"', embed)
            candidate = src_match.group(1) if src_match else embed
            # Extract numeric ID from common Vimeo patterns
            id_match = re.search(r'(?:player\.vimeo\.com\/video\/|vimeo\.com\/)(\d+)', candidate)
            if id_match:
                video_id = id_match.group(1)
                # Normalize to player embed URL
                cleaned['vimeo_url'] = f"https://player.vimeo.com/video/{video_id}"
                url_f = cleaned['vimeo_url']
            else:
                # If no ID found but src looks like a player URL, accept it
                if 'player.vimeo.com' in candidate:
                    cleaned['vimeo_url'] = candidate
                    url_f = candidate
                else:
                    raise ValidationError("Could not parse Vimeo embed code. Please paste the full iframe code.")

        if c_type == 'pdf':
            if not file_f:
                raise ValidationError("Upload a PDF file.")
            if file_f.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise ValidationError(f"PDF must be ≤ {MAX_FILE_SIZE_MB}\u202fMB.")
        elif c_type == 'video' and not url_f:
            raise ValidationError("Provide a Vimeo embed code for videos.")
        elif c_type == 'pdf_video':
            # Require both
            if not file_f:
                raise ValidationError("Upload a PDF file (for PDF + Video).")
            if file_f.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise ValidationError(f"PDF must be ≤ {MAX_FILE_SIZE_MB}\u202fMB.")
            if not url_f:
                raise ValidationError("Provide a Vimeo embed code (for PDF + Video).")
        return cleaned


class CampaignCollateralForm(forms.ModelForm):
    class Meta:
        model  = CampaignCollateral
        fields = ['campaign', 'collateral', 'start_date', 'end_date']


class CollateralMessageForm(forms.ModelForm):
    """Form for adding custom WhatsApp messages for specific collaterals"""
    
    class Meta:
        model = CollateralMessage
        fields = ['campaign', 'collateral', 'message', 'is_active']
        widgets = {
            'campaign': forms.Select(attrs={'class': 'form-control', 'id': 'campaign-select'}),
            'collateral': forms.Select(attrs={'class': 'form-control', 'id': 'collateral-select'}),
            'message': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 8, 
                'placeholder': 'Enter your custom WhatsApp message here. Use $collateralLinks as placeholder for the actual link.',
                'id': 'message-textarea'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter campaigns to only active ones
        try:
            self.fields['campaign'].queryset = Campaign.objects.filter(is_active=True).order_by('brand_campaign_id')
        except FieldError:
            # Some deployments use Campaign.status instead of an is_active boolean.
            # Fall back to showing all campaigns rather than 500'ing.
            self.fields['campaign'].queryset = Campaign.objects.all().order_by('brand_campaign_id')
        self.fields['campaign'].empty_label = "Select Campaign"
        
        # Initially empty collateral queryset - will be populated via JavaScript
        self.fields['collateral'].queryset = Collateral.objects.none()
        self.fields['collateral'].empty_label = "First select a campaign"
    
    def clean(self):
        cleaned_data = super().clean()
        campaign = cleaned_data.get('campaign')
        collateral = cleaned_data.get('collateral')
        
        # Check if message already exists for this campaign-collateral combination
        if campaign and collateral:
            existing_message = CollateralMessage.objects.filter(
                campaign=campaign, 
                collateral=collateral
            ).exclude(pk=self.instance.pk if self.instance.pk else None)
            
            if existing_message.exists():
                raise forms.ValidationError(
                    f"A message already exists for {campaign.brand_campaign_id} - {collateral.title}. "
                    "Please edit the existing message instead of creating a duplicate."
                )
        
        return cleaned_data


class CollateralMessageSearchForm(forms.Form):
    """Form for searching existing collateral messages"""
    brand_campaign_id = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter Brand Campaign ID (e.g., test2323)'
        })
    )
    collateral_id = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter Collateral ID'
        })
    )


