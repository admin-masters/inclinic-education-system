# ── ADD / REPLACE THIS WHOLE FILE ─────────────────────────────
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
    collateral        = forms.ModelChoiceField(
        queryset=Collateral.objects.filter(is_active=True),
        label="Select Collateral",
    )
    doctor_contact    = forms.CharField(            # one field for all channels
        max_length=255,
        label="Phone / E-mail",
    )
    share_channel     = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        initial="WhatsApp",
    )
    message_text      = forms.CharField(            # optional custom message
        widget=forms.Textarea,
        required=False,
        label="Custom Message (optional)",
    )

    # ----------  extra validation so user can’t mix channels  ----------
    def clean(self):
        cleaned = super().clean()
        chan  = cleaned.get("share_channel")
        value = (cleaned.get("doctor_contact") or "").strip()

        if not value:
            raise ValidationError("Please enter the recipient’s phone or e-mail.")

        if chan == "Email":
            try:
                validate_email(value)
            except ValidationError:
                raise ValidationError("Enter a valid e-mail address.")
        else:  # phone-like: keep digits only so +91-xxx OK, letters not
            digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
            if len(digits) < 8:
                raise ValidationError("Enter a valid phone number.")
            cleaned["doctor_contact"] = digits   # normalised phone

        return cleaned
