from django import forms
from django.core.exceptions import ValidationError
from collateral_management.models import Collateral

class ShareForm(forms.Form):
    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.filter(is_active=True),
        label="Select Collateral"
    )
    doctor_identifier = forms.CharField(max_length=255, label="Doctor Phone or Name")
    share_channel = forms.ChoiceField(choices=(('WhatsApp','WhatsApp'),('SMS','SMS'),('Email','Email')), initial='WhatsApp')

    # Optional: if you want a custom message
    message_text = forms.CharField(widget=forms.Textarea, required=False, label="Custom Message (optional)")
