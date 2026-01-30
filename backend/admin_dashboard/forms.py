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

class FieldRepForm(forms.ModelForm):
    """
    FieldRep create/edit form:
    - Captures first_name + last_name as input.
    - Enforces: same email cannot exist for the SAME BRAND (brand derived from master campaign).
    """

    first_name = forms.CharField(
        required=True,
        label="First Name",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
    )
    last_name = forms.CharField(
        required=True,
        label="Last Name",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
    )

    phone_number = forms.CharField(
        validators=[PHONE_RE],
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "+919876543210"
        }),
        label="Field Rep Number"
    )

    _UUID32_RE = re.compile(r"^[0-9a-fA-F]{32}$")

    def __init__(self, *args, campaign_param=None, **kwargs):
        """
        campaign_param is passed from the view (GET/POST campaign context).
        We use it to find the master Brand and enforce email uniqueness per brand.
        """
        self.campaign_param = (str(campaign_param).strip() if campaign_param else "")
        super().__init__(*args, **kwargs)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number", "field_id")
        labels = {
            "email": "Gmail ID",
            "field_id": "Field ID",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "field_id": forms.TextInput(attrs={"class": "form-control"}),
        }

    # ---------------------------
    # Brand-aware duplicate checks
    # ---------------------------

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            return email

        # Figure out which master brand(s) this rep belongs to:
        # 1) brand from current campaign context (GET/POST)
        # 2) brand(s) inferred from existing campaign assignments (edit case)
        brand_ids = set()

        brand_id_ctx = self._master_brand_id_from_campaign_param(self.campaign_param)
        if brand_id_ctx:
            brand_ids.add(str(brand_id_ctx))

        if self.instance and self.instance.pk:
            for bid in self._master_brand_ids_from_existing_assignments(self.instance.pk):
                if bid:
                    brand_ids.add(str(bid))

        # If we can't determine brand, we can't enforce brand-scoped uniqueness.
        # (Usually campaign context is present in admin flows.)
        if not brand_ids:
            return email

        for brand_id in brand_ids:
            if self._email_exists_in_brand(email=email, brand_id=brand_id):
                raise forms.ValidationError(
                    "Field rep already exist with the same email try using different email."
                )

        return email

    def _master_alias(self) -> str:
        return getattr(settings, "MASTER_DB_ALIAS", "master")

    def _normalize_campaign_id_to_master_id(self, raw: str) -> str | None:
        """
        Accepts:
        - dashed UUID: f44996be-1937-4f5e-95ae-5f1bb333b66c
        - 32-hex:     f44996be19374f5e95ae5f1bb333b66c
        Returns 32-hex master id or None.
        """
        if not raw:
            return None
        s = str(raw).strip()
        if not s:
            return None

        if self._UUID32_RE.fullmatch(s):
            return s.lower()

        try:
            return uuid.UUID(s).hex  # 32-hex
        except Exception:
            return None

    def _master_brand_id_from_campaign_param(self, campaign_param: str) -> str | None:
        """
        campaign_param might be:
        - brand_campaign_id UUID string (preferred)
        - numeric portal campaign pk (older links)
        """
        if not campaign_param:
            return None

        # If numeric, try resolving to brand_campaign_id first
        cp = str(campaign_param).strip()
        if cp.isdigit():
            try:
                from campaign_management.models import Campaign
                bc = Campaign.objects.filter(pk=int(cp)).values_list("brand_campaign_id", flat=True).first()
                if bc:
                    cp = str(bc)
            except Exception:
                return None

        master_id = self._normalize_campaign_id_to_master_id(cp)
        if not master_id:
            return None

        try:
            alias = self._master_alias()
            return (
                MasterCampaign.objects.using(alias)
                .filter(id=master_id)
                .values_list("brand_id", flat=True)
                .first()
            )
        except Exception:
            return None

    def _master_brand_ids_from_existing_assignments(self, user_id: int) -> list[str]:
        """
        For edits where campaign_param may be missing, infer brand(s) from the rep's
        existing campaign assignments (FieldRepCampaign -> Campaign.brand_campaign_id -> MasterCampaign.brand_id).
        """
        try:
            assigned_brand_campaign_ids = list(
                FieldRepCampaign.objects
                .filter(field_rep_id=user_id)
                .values_list("campaign__brand_campaign_id", flat=True)
                .distinct()
            )
        except Exception:
            return []

        master_ids = []
        for bc in assigned_brand_campaign_ids:
            mid = self._normalize_campaign_id_to_master_id(str(bc))
            if mid:
                master_ids.append(mid)

        if not master_ids:
            return []

        try:
            alias = self._master_alias()
            return list(
                MasterCampaign.objects.using(alias)
                .filter(id__in=master_ids)
                .values_list("brand_id", flat=True)
                .distinct()
            )
        except Exception:
            return []

    def _portal_brand_campaign_ids_for_master_brand(self, brand_id: str) -> list[str]:
        """
        Return candidate brand_campaign_id strings in BOTH forms:
        - 32-hex (master id)
        - dashed UUID
        so it matches whatever is stored in portal Campaign.brand_campaign_id.
        """
        alias = self._master_alias()
        master_ids = list(
            MasterCampaign.objects.using(alias)
            .filter(brand_id=brand_id)
            .values_list("id", flat=True)
        )

        out = []
        for mid in master_ids:
            mid_str = str(mid).strip()
            if not mid_str:
                continue
            out.append(mid_str)
            if self._UUID32_RE.fullmatch(mid_str):
                try:
                    out.append(str(uuid.UUID(hex=mid_str)))
                except Exception:
                    pass

        # De-dupe preserving order
        seen = set()
        uniq = []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    def _email_exists_in_brand(self, email: str, brand_id: str) -> bool:
        """
        Checks if there exists ANY OTHER field rep (User) with same email (case-insensitive)
        assigned to ANY campaign that belongs to the same master Brand.
        """
        try:
            brand_campaign_ids = self._portal_brand_campaign_ids_for_master_brand(brand_id)
            if not brand_campaign_ids:
                return False

            qs = FieldRepCampaign.objects.filter(
                campaign__brand_campaign_id__in=brand_campaign_ids,
                field_rep__role="field_rep",
                field_rep__email__iexact=email,
            )

            if self.instance and self.instance.pk:
                qs = qs.exclude(field_rep_id=self.instance.pk)

            return qs.exists()
        except Exception:
            return False

    # ---------------------------
    # Save behavior (unchanged + role)
    # ---------------------------
    def save(self, commit=True):
        user = super().save(commit=False)

        # Set role to field_rep
        user.role = "field_rep"

        # Generate username from email if not set
        if not user.username:
            base_username = user.email.split("@")[0]
            username = base_username
            counter = 1

            while User.objects.filter(username=username).exists():
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
