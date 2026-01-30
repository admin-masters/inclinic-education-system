import csv, io, re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from user_management.models import User  # custom user
from doctor_viewer.models import Doctor
from campaign_management.models import Campaign, CampaignAssignment
from admin_dashboard.models import FieldRepCampaign
import uuid
from django.conf import settings
from campaign_management.master_models import MasterCampaign


PHONE_RE_CSV = re.compile(r'^\+?\d{8,15}$')  # naive validation for CSV

# ------------------------------------------------------------------
# BULK UPLOAD FIELD REPS VIA CSV
# ------------------------------------------------------------------
class FieldRepBulkUploadForm(forms.Form):
    """
    CSV with: name,email,phone
    (No header row required but allowed.)
    """
    csv_file = forms.FileField(help_text="CSV: name,email,phone – max 2 MB")
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.all(),
        required=False,
        help_text="Optional: Assign all field reps in this upload to a specific campaign"
    )

    def clean_csv_file(self):
        f = self.cleaned_data['csv_file']
        if f.size > 2*1024*1024:
            raise ValidationError("CSV larger than 2 MB.")
        return f

    def save(self, admin_user):
        """
        Returns (created_count, updated_count, campaign_assignments, errors[list]).
        """
        file_obj = io.StringIO(self.cleaned_data['csv_file'].read().decode())
        reader = csv.reader(file_obj)
        created = updated = campaign_assignments = 0
        errors = []
        campaign = self.cleaned_data.get('campaign')

        for row_num, row in enumerate(reader, start=1):
            if not row or row[0].strip().lower() in ('name', ''):
                continue  # skip header/blank
            try:
                name, email, phone = [c.strip() for c in row]
                if not PHONE_RE_CSV.match(phone):
                    raise ValueError("Bad phone format")
                
                # Split name into first_name and last_name
                name_parts = name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''
                
                obj, is_new = User.objects.update_or_create(
                    email=email,
                    defaults={
                        'username': email.split('@')[0],
                        'first_name': first_name,
                        'last_name': last_name,
                        'phone_number': phone,
                        'role': 'field_rep',
                        'active': True,
                    }
                )
                created += 1 if is_new else 0
                updated += 0 if is_new else 1
                
                # Create campaign assignment if campaign is specified
                if campaign and obj:
                    # Create CampaignAssignment for field rep portal
                    assignment, assignment_created = CampaignAssignment.objects.get_or_create(
                        field_rep=obj,
                        campaign=campaign
                    )
                    if assignment_created:
                        campaign_assignments += 1
                    
                    # Also create FieldRepCampaign for admin dashboard compatibility
                    FieldRepCampaign.objects.get_or_create(
                        field_rep=obj,
                        campaign=campaign
                    )
                    
            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")

        return created, updated, campaign_assignments, errors

# ------------------------------------------------------------------
# SINGLE FIELD-REP FORM (email · phone · field_id)
# ------------------------------------------------------------------
PHONE_RE = RegexValidator(r'^\+?\d{7,15}$')

import re
import uuid
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from user_management.models import User
from campaign_management.models import Campaign, CampaignAssignment
from admin_dashboard.models import FieldRepCampaign
from campaign_management.master_models import MasterCampaign

PHONE_RE = RegexValidator(regex=r'^\+?\d{8,15}$', message="Enter a valid phone number (8–15 digits, optional +).")


class FieldRepForm(forms.ModelForm):
    """
    Portal FieldRep user create/update form.

    Adds:
    - first_name, last_name inputs
    - brand-scoped email uniqueness check (based on master brand derived from selected campaign)
    """

    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
        label="First Name",
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
        label="Last Name",
    )

    phone_number = forms.CharField(
        validators=[PHONE_RE],
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "+919876543210",
        }),
        label="Field Rep Number",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number", "field_id")
        labels = {
            "email": "Gmail ID",
            "field_id": "Field ID",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@gmail.com"}),
            "field_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "Field ID"}),
        }

    def __init__(self, *args, campaign_param=None, **kwargs):
        """
        campaign_param is the brand campaign id coming from GET/POST 'campaign' (string).
        We keep it as a *string* and always strip whitespace to avoid UUID parsing crashes.
        """
        self.campaign_param = (str(campaign_param).strip() if campaign_param else "")
        super().__init__(*args, **kwargs)

    # -----------------------------
    # Brand-aware email validation
    # -----------------------------
    @staticmethod
    def _normalize_to_brand_campaign_id(value):
        """
        Accepts:
        - numeric campaign pk -> converts to Campaign.brand_campaign_id
        - otherwise returns as stripped string
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None

        # numeric pk -> fetch campaign row
        if s.isdigit():
            try:
                c = Campaign.objects.only("brand_campaign_id").get(pk=int(s))
                return str(c.brand_campaign_id).strip() if c.brand_campaign_id else None
            except Exception:
                return None

        return s

    @staticmethod
    def _brand_id_from_brand_campaign_id(brand_campaign_id):
        """
        brand_campaign_id is expected to be a UUID string (with or without dashes).
        MasterCampaign.id is stored as *dashless* 32-char hex.
        """
        if not brand_campaign_id:
            return None

        raw = str(brand_campaign_id).strip()
        if not raw:
            return None

        try:
            mc_id = uuid.UUID(raw).hex  # dashless 32
        except Exception:
            return None

        mc = (
            MasterCampaign.objects.using("master")
            .filter(id=mc_id)
            .only("brand_id")
            .first()
        )
        return str(mc.brand_id) if mc and getattr(mc, "brand_id", None) else None

    @staticmethod
    def _dashed_campaign_ids_for_brand(brand_id):
        """
        For a master brand_id, return all related campaign UUIDs (dashed string form)
        so they match Campaign.brand_campaign_id stored in default DB.
        """
        if not brand_id:
            return []

        master_ids = list(
            MasterCampaign.objects.using("master")
            .filter(brand_id=str(brand_id))
            .values_list("id", flat=True)
        )

        dashed = []
        for mid in master_ids:
            if not mid:
                continue
            try:
                dashed.append(str(uuid.UUID(hex=str(mid))))
            except Exception:
                # If master stores already dashed for some reason
                try:
                    dashed.append(str(uuid.UUID(str(mid))))
                except Exception:
                    continue

        return dashed

    @staticmethod
    def _email_exists_for_brand(email, brand_id, exclude_user_pk=None):
        """
        A portal-side check:
        - Find all campaigns of that brand from master DB
        - Find all field reps assigned to any of those campaigns in default DB
        - Check if any other field rep has the same email (case-insensitive)
        """
        if not email or not brand_id:
            return False

        dashed_campaign_ids = FieldRepForm._dashed_campaign_ids_for_brand(brand_id)
        if not dashed_campaign_ids:
            return False

        # Reps assigned via CampaignAssignment and/or FieldRepCampaign
        rep_ids = set(
            CampaignAssignment.objects.filter(
                campaign__brand_campaign_id__in=dashed_campaign_ids
            ).values_list("field_rep_id", flat=True)
        )
        rep_ids |= set(
            FieldRepCampaign.objects.filter(
                campaign__brand_campaign_id__in=dashed_campaign_ids
            ).values_list("field_rep_id", flat=True)
        )

        if not rep_ids:
            return False

        qs = User.objects.filter(role="field_rep", id__in=rep_ids, email__iexact=email)
        if exclude_user_pk:
            qs = qs.exclude(pk=exclude_user_pk)
        return qs.exists()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            return email

        # 1) Prefer current campaign selection
        brand_campaign_id = self._normalize_to_brand_campaign_id(self.campaign_param)
        brand_ids_to_check = []

        if brand_campaign_id:
            bid = self._brand_id_from_brand_campaign_id(brand_campaign_id)
            if bid:
                brand_ids_to_check.append(bid)

        # 2) If editing and no campaign context, infer from existing assignments
        if self.instance and self.instance.pk:
            try:
                assigned_campaigns = set(
                    CampaignAssignment.objects.filter(field_rep_id=self.instance.pk)
                    .values_list("campaign__brand_campaign_id", flat=True)
                )
                assigned_campaigns |= set(
                    FieldRepCampaign.objects.filter(field_rep_id=self.instance.pk)
                    .values_list("campaign__brand_campaign_id", flat=True)
                )
            except Exception:
                assigned_campaigns = set()

            for cid in assigned_campaigns:
                cid_norm = self._normalize_to_brand_campaign_id(cid)
                bid = self._brand_id_from_brand_campaign_id(cid_norm)
                if bid and bid not in brand_ids_to_check:
                    brand_ids_to_check.append(bid)

        # Validate for each brand we could resolve
        exclude_pk = self.instance.pk if self.instance and self.instance.pk else None
        for bid in brand_ids_to_check:
            if self._email_exists_for_brand(email=email, brand_id=bid, exclude_user_pk=exclude_pk):
                raise ValidationError("Field rep already exist with the same email try using different email.")

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        # Ensure role
        user.role = "field_rep"
        user.active = True

        # Generate username from email if not set
        if not user.username:
            base_username = (user.email or "").split("@")[0] or "fieldrep"
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exclude(pk=user.pk).exists():
                username = f"{base_username}_{counter}"
                counter += 1
            user.username = username

        if commit:
            user.save()
        return user



# ------------------------------------------------------------------
# DOCTOR FORM
# ------------------------------------------------------------------
class DoctorForm(forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ("name", "phone")
        labels = {
            "name": "Doctor Name:",
            "phone": "Doctor Number:",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
        }
