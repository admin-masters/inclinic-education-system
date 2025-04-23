# shortlink_management/forms.py

from django import forms
from .models import ShortLink
from collateral_management.models import Collateral
from .utils import generate_short_code

class ShortLinkForm(forms.ModelForm):
    """
    Allows admin to select a Collateral, automatically sets resource_type='collateral'.
    """
    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.filter(is_active=True),
        label="Select Collateral"
    )

    class Meta:
        model = ShortLink
        fields = ['short_code', 'is_active']
        # We'll store resource_type & resource_id behind the scenes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # short_code is optional for the admin to override
        self.fields['short_code'].required = False

    def clean(self):
        cleaned_data = super().clean()
        short_code = cleaned_data.get('short_code', '')
        if not short_code:
            # auto-generate
            short_code = generate_short_code()
            cleaned_data['short_code'] = short_code
        return cleaned_data