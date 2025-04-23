# collateral_management/forms.py

from django import forms
from .models import Collateral, CampaignCollateral
from django.core.exceptions import ValidationError
from django.conf import settings

MAX_FILE_SIZE_MB = 2

class CollateralForm(forms.ModelForm):
    """
    For creating/updating Collateral.
    We'll enforce the 2 MB limit for PDFs if type='pdf'.
    """

    class Meta:
        model = Collateral
        fields = [
            'type', 'title', 'file', 'vimeo_url',
            'content_id', 'is_active',
        ]

    def clean(self):
        cleaned_data = super().clean()
        collateral_type = cleaned_data.get('type')
        file_field = cleaned_data.get('file')
        vimeo_url = cleaned_data.get('vimeo_url')

        # If collateral_type is PDF, ensure file is present and <= 2MB
        if collateral_type == 'pdf':
            if not file_field:
                raise ValidationError("You must upload a PDF file for type=pdf.")
            if file_field.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise ValidationError(
                    f"PDF size must not exceed {MAX_FILE_SIZE_MB} MB."
                )
            # Optionally, you can also check extension, e.g. .pdf

        # If collateral_type is video, ensure vimeo_url is provided
        if collateral_type == 'video':
            if not vimeo_url:
                raise ValidationError("You must provide a Vimeo URL for type=video.")

        return cleaned_data


class CampaignCollateralForm(forms.ModelForm):
    """
    For linking an existing Collateral to a Campaign.
    """
    class Meta:
        model = CampaignCollateral
        fields = ['campaign', 'collateral', 'start_date', 'end_date']