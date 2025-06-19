from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from collateral_management.models import Collateral

CHANNEL_CHOICES = (
    ("WhatsApp", "WhatsApp"),
    ("SMS",      "SMS"),
    ("Email",    "Email"),
)

class ShareForm(forms.Form):
    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.filter(is_active=True),
        label="Select Collateral",
    )
    doctor_contact = forms.CharField(
        max_length=255,
        label="Phone / E-mail",
    )
    share_channel = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        initial="WhatsApp",
    )
    message_text = forms.CharField(
        widget=forms.Textarea,
        required=False,
        label="Custom Message (optional)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add Bootstrap 5 classes
        self.fields['collateral'].widget.attrs.update({
            'class': 'form-select'
        })
        self.fields['doctor_contact'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': '+91XXXXXXXXXX or doctor@example.com'
        })
        self.fields['share_channel'].widget.attrs.update({
            'class': 'form-select'
        })
        self.fields['message_text'].widget.attrs.update({
            'class': 'form-control',
            'rows': '4',
            'placeholder': 'Write a message (optional)'
        })

    def clean(self):
        cleaned = super().clean()
        chan = cleaned.get("share_channel")
        value = (cleaned.get("doctor_contact") or "").strip()

        if not value:
            raise ValidationError("Please enter the recipient’s phone or e-mail.")

        if chan == "Email":
            try:
                validate_email(value)
            except ValidationError:
                raise ValidationError("Enter a valid e-mail address.")
        else:
            digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
            if len(digits) < 8:
                raise ValidationError("Enter a valid phone number.")
            cleaned["doctor_contact"] = digits

        return cleaned
