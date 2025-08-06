# collateral_management/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import Collateral
from campaign_management.models import CampaignCollateral

class CampaignCollateralDateForm(forms.ModelForm):
    class Meta:
        model = CampaignCollateral
        fields = ['start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
MAX_FILE_SIZE_MB = 2

TITLE_CHOICES = [
    ('Doctor education short',  'Doctor education short'),
    ('Doctor education long',   'Doctor education long'),
    ('Patient education compliance', 'Patient education compliance'),
    ('Patient education general',    'Patient education general'),
]

class CollateralForm(forms.ModelForm):
    # ── UI overrides / extra inputs ──────────────────────────────────────────
    title = forms.ChoiceField(
        choices=[('', 'Select Purpose of the Collateral')] + TITLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
        label="Purpose of the Collateral"
    )
    banner_1    = forms.ImageField(required=False)
    banner_2    = forms.ImageField(required=False)
    description = forms.CharField(max_length=255, required=False)
    # purpose field removed

    class Meta:
        model  = Collateral
        fields = [
            'campaign',      # <- will be set/validated in the view
            'title', 'type', 'file', 'vimeo_url',
            'content_id', 'banner_1', 'banner_2', 'description',
            'is_active',
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



