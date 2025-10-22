# collateral_management/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import Collateral, CampaignCollateral
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

    class Meta:
        model  = Collateral
        fields = [
            'campaign', 'purpose', 'title', 'content_id', 'type',
            'file', 'vimeo_url',
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

        if c_type == 'pdf':
            if not file_f:
                raise ValidationError("Upload a PDF file.")
            if file_f.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise ValidationError(f"PDF must be ≤ {MAX_FILE_SIZE_MB} MB.")
        elif c_type == 'video' and not url_f:
            raise ValidationError("Provide a Vimeo URL for videos.")
        return cleaned


class CampaignCollateralForm(forms.ModelForm):
    class Meta:
        model  = CampaignCollateral
        fields = ['campaign', 'collateral', 'start_date', 'end_date']



