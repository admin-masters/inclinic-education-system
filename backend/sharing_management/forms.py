import csv, io, re
import logging

from django.db import transaction
from datetime import datetime, timedelta
from django import forms
from django.db.models import Q, Count, Max, Case, When, Value, BooleanField
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.text import slugify
from django.utils.safestring import mark_safe
from user_management.models import User
from doctor_viewer.models import Doctor, DoctorCollateral, DoctorEngagement
from collateral_management.models import Collateral
from collateral_management.models import CampaignCollateral as CMCampaignCollateral
from campaign_management.models import Campaign
from .models import ShareLog

# ─── Common constants ──────────────────────────────────────────────────────────
CHANNEL_CHOICES = (
    ("WhatsApp", "WhatsApp"),
    ("SMS",      "SMS"),
    ("Email",    "Email"),
)

class DoctorChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} ({obj.phone or 'No phone'})"

class ShareForm(forms.Form):

    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.none(),
        label="Select Collateral",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )

    existing_doctor = forms.ModelChoiceField(
        queryset=Doctor.objects.none(),
        required=False,
        label="Select Existing Doctor",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    new_doctor_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    doctor_contact = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    share_channel = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        initial="WhatsApp",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    message_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    # Main fields
    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.filter(is_active=True).order_by('-created_at'),
        label="Select Collateral",
        help_text="Most recent collateral is pre-selected",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'hx-get': '/update-doctors-list/',
            'hx-trigger': 'change',
            'hx-target': '#doctors-list-container',
        })
    )
    
    # Doctor selection (existing or new)
    existing_doctor = forms.ModelChoiceField(
        queryset=Doctor.objects.none(),
        required=False,
        label="Select Existing Doctor",
        widget=forms.Select(attrs={
            'class': 'form-select select2',
            'data-placeholder': 'Search for a doctor...',
            'hx-get': '/update-doctor-status/',
            'hx-trigger': 'change',
            'hx-target': '#doctor-status',
        })
    )
    
    # New doctor fields
    new_doctor_name = forms.CharField(
        max_length=100,
        required=False,
        label="Or Add New Doctor",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Doctor Name',
            'hx-trigger': 'keyup changed',
            'hx-get': '/check-doctor-exists/',
            'hx-target': '#doctor-exists-message',
        })
    )
    
    doctor_contact = forms.CharField(
        max_length=20,
        required=False,
        label="Doctor's Contact",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+91XXXXXXXXXX',
        })
    )
    
    # Sharing options
    share_channel = forms.ChoiceField(
        choices=CHANNEL_CHOICES,
        initial="WhatsApp",
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    
    message_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': '3',
            'placeholder': 'Add a personalized message (optional)',
        }),
        required=False,
        label="Message"
    )
    
    # Filtering and search
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search doctors...',
            'hx-get': '/doctors/search/',
            'hx-trigger': 'keyup changed delay:500ms',
            'hx-target': '#doctors-list',
        })
    )
    
    status_filter = forms.ChoiceField(
        choices=[
            ('all', 'All Doctors'),
            ('needs_share', 'Needs Sharing'),
            ('needs_reminder', 'Needs Reminder'),
            ('shared', 'Already Shared'),
        ],
        initial='all',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'hx-get': '/doctors/filter/',
            'hx-trigger': 'change',
            'hx-target': '#doctors-list',
        })
    )

    def __init__(self, user, *args, **kwargs):
        brand_campaign_id = kwargs.pop('brand_campaign_id', None)
        super().__init__(*args, **kwargs)

        self.user = user
        from django.utils import timezone
        from django.db.models import Q
        from campaign_management.models import Campaign
        from collateral_management.models import CampaignCollateral as CMCampaignCollateral

        today = timezone.now().date()

        # --------------------------------------------------
        # STEP 1: Filter collaterals safely
        # --------------------------------------------------
        if brand_campaign_id:
            try:
                campaign = Campaign.objects.get(brand_campaign_id=brand_campaign_id)

                cc_qs = CMCampaignCollateral.objects.filter(
                    campaign=campaign,
                    collateral__is_active=True
                ).filter(
                    Q(start_date__isnull=True) | Q(start_date__lte=today),
                    Q(end_date__isnull=True) | Q(end_date__gte=today),
                )

                self.fields['collateral'].queryset = Collateral.objects.filter(
                    id__in=cc_qs.values_list('collateral_id', flat=True),
                    is_active=True
                ).order_by('-created_at')

            except Campaign.DoesNotExist:
                self.fields['collateral'].queryset = Collateral.objects.none()
        else:
            # No campaign = no collaterals (important for safety)
            self.fields['collateral'].queryset = Collateral.objects.none()

        # --------------------------------------------------
        # STEP 2: Default select latest active collateral
        # --------------------------------------------------
        latest = self.fields['collateral'].queryset.first()
        if latest:
            self.fields['collateral'].initial = latest

        # --------------------------------------------------
        # STEP 3: Load doctors for this rep
        # --------------------------------------------------
        self.fields['existing_doctor'].queryset = Doctor.objects.filter(
            rep=user
        ).order_by('name')

    # --------------------------------------------------
    # STEP 4: Final server-side validation
    # --------------------------------------------------
    def clean_collateral(self):
        collateral = self.cleaned_data.get('collateral')

        if not collateral or not collateral.is_active:
            raise forms.ValidationError("Invalid collateral selected.")

        return collateral

    
    def get_doctors_with_status(self):
        """Get doctors with their sharing status for the selected collateral"""
        collateral = self.initial.get('collateral') or self.data.get('collateral')
        
        # Get all doctors assigned to the current user (field rep)
        doctors = Doctor.objects.filter(rep=self.user)
        
        # Get sharing status for each doctor
        if collateral:
            # Get share logs for this collateral
            shared_doctor_ids = ShareLog.objects.filter(
                field_rep=self.user,
                collateral_id=collateral.id if hasattr(collateral, 'id') else collateral
            ).values_list('doctor_identifier', flat=True)
            
            # Get engagement data for this collateral
            engaged_doctor_ids = DoctorEngagement.objects.filter(
                short_link__resource_id=collateral.id if hasattr(collateral, 'id') else collateral,
                short_link__resource_type='collateral'
            ).values_list('doctor__id', flat=True)
            
            # Annotate doctors with their status
            doctors = doctors.annotate(
                is_shared=Case(
                    When(id__in=shared_doctor_ids, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                ),
                has_engaged=Case(
                    When(id__in=engaged_doctor_ids, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                ),
                last_shared=Max('share_logs__share_timestamp')
            )
        
        return doctors
    
    def clean(self):
        cleaned_data = super().clean()

        existing_doctor = cleaned_data.get('existing_doctor')
        new_doctor_name = cleaned_data.get('new_doctor_name')
        doctor_contact = cleaned_data.get('doctor_contact')

        if not existing_doctor and not (new_doctor_name and doctor_contact):
            raise forms.ValidationError(
                "Please select an existing doctor or enter new doctor details."
            )

        if existing_doctor and (new_doctor_name or doctor_contact):
            raise forms.ValidationError(
                "Choose either an existing doctor OR enter new doctor details."
            )

        return cleaned_data

# ─── Calendar update form for Campaign ↔ Collateral (bridging in collateral_management) ───
class CalendarCampaignCollateralForm(forms.ModelForm):
    campaign = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly',
            'style': 'background-color: #e9ecef; cursor: not-allowed;'
        }),
        label="Brand Campaign ID",
        disabled=True
    )
    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.none(),
        label="Select Collateral",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = CMCampaignCollateral
        fields = ['collateral', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        brand_campaign_id = kwargs.pop('brand_campaign_id', None)
        super().__init__(*args, **kwargs)

        # Determine campaign context
        campaign_obj = None
        if brand_campaign_id:
            try:
                campaign_obj = Campaign.objects.get(brand_campaign_id=brand_campaign_id)
                self.fields['campaign'].initial = campaign_obj.brand_campaign_id
            except Campaign.DoesNotExist:
                pass

        if self.instance and self.instance.pk and not campaign_obj:
            campaign_obj = self.instance.campaign
            if campaign_obj:
                self.fields['campaign'].initial = campaign_obj.brand_campaign_id

        # Build collateral queryset
        collaterals = Collateral.objects.none()
        if campaign_obj:
            direct = Collateral.objects.filter(campaign=campaign_obj)
            via_bridge = Collateral.objects.filter(campaign_collaterals__campaign=campaign_obj)
            collaterals = (direct | via_bridge).distinct()
            if self.instance and self.instance.pk and self.instance.collateral:
                current = self.instance.collateral
                if not collaterals.filter(pk=current.pk).exists():
                    collaterals = collaterals | Collateral.objects.filter(pk=current.pk)
        else:
            collaterals = Collateral.objects.all()

        self.fields['collateral'].queryset = collaterals.order_by('title')
        if self.instance and self.instance.pk and self.instance.collateral:
            self.fields['collateral'].initial = self.instance.collateral

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date cannot be earlier than start date.")

        # Validate campaign presence for new records
        if not self.instance.pk:
            bcid = cleaned_data.get('campaign') or self.fields['campaign'].initial
            if not bcid:
                raise ValidationError("Brand Campaign ID is required for new campaign collateral.")
            try:
                Campaign.objects.get(brand_campaign_id=bcid)
            except Campaign.DoesNotExist:
                raise ValidationError(f"Campaign with Brand Campaign ID '{bcid}' not found.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Preserve or set campaign by brand_campaign_id
        if self.instance and self.instance.pk:
            instance.campaign = self.instance.campaign
        else:
            bcid = self.cleaned_data.get('campaign') or self.fields['campaign'].initial
            if bcid:
                try:
                    instance.campaign = Campaign.objects.get(brand_campaign_id=bcid)
                except Campaign.DoesNotExist:
                    raise ValidationError(f"Campaign with Brand Campaign ID '{bcid}' not found.")

        # Convert date inputs to DateTime at start/end of day
        sd = self.cleaned_data.get('start_date')
        ed = self.cleaned_data.get('end_date')
        if sd and not hasattr(sd, 'hour'):
            instance.start_date = timezone.make_aware(datetime.combine(sd, datetime.min.time()))
        if ed and not hasattr(ed, 'hour'):
            instance.end_date = timezone.make_aware(datetime.combine(ed, datetime.max.time().replace(microsecond=0)))

        if commit:
            instance.save()
        return instance


# ─── Bulk *manual* share (existing) ────────────────────────────────────────────
class BulkManualShareForm(forms.Form):
    """
    Expects a CSV with header row:

    Option 1: For field reps only (2 columns):
      Field Rep ID, Gmail ID

    Option 2: Full format (6 columns):
      field_rep_email, doctor_name, doctor_contact, collateral_id,
      share_channel (WhatsApp/SMS/Email), message_text(optional)
    """
    csv_file = forms.FileField(
        help_text=("CSV Format 1: Field Rep ID, Gmail ID<br>"
                   "CSV Format 2: field_rep_email,doctor_name,doctor_contact,"
                   "collateral_id,share_channel,message_text"),
    )

    MAX_SIZE = 2 * 1024 * 1024  # 2 MB

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("CSV larger than 2 MB")
        return f

    def save(self, *, user_request, campaign=None):
        """
        Returns:
            created_count, all_messages, errors
        """
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from datetime import timedelta
        from campaign_management.models import CampaignAssignment
        from admin_dashboard.models import FieldRepCampaign
        from shortlink_management.models import ShortLink
        from shortlink_management.utils import generate_short_code

        UserModel = get_user_model()

        data = self.cleaned_data["csv_file"].read().decode()
        file_obj = io.StringIO(data)

        peek = next(csv.reader(io.StringIO(data)), [])
        header_keys_2 = {"field rep id", "gmail id", "field_rep_id", "gmail_id"}
        header_keys_6 = {"field_rep_email", "doctor_name", "doctor_contact",
                         "collateral_id", "share_channel", "message_text"}

        is_2_col_format = any((c or "").strip().lower() in header_keys_2 for c in peek[:2])
        is_6_col_format = any((c or "").strip().lower() in header_keys_6 for c in peek)

        created = 0
        errors = []
        success_messages = []

        # ---------------- 2 COLUMN FORMAT ----------------
        if is_2_col_format:
            file_obj.seek(0)
            reader = csv.DictReader(file_obj)

            for row_no, r in enumerate(reader, start=2):
                field_rep_id = (r.get("Field Rep ID") or r.get("field_rep_id") or "").strip()
                gmail_id = (r.get("Gmail ID") or r.get("gmail_id") or "").strip()

                if not field_rep_id and not gmail_id:
                    continue

                try:
                    rep = None

                    if field_rep_id:
                        rep = UserModel.objects.filter(role="field_rep", field_id__iexact=field_rep_id).first()

                    if not rep and gmail_id:
                        rep = UserModel.objects.filter(role="field_rep", email__iexact=gmail_id).first()

                    # AUTO-CREATE FIELD REP
                    if not rep:
                        from django.contrib.auth.hashers import make_password
                        import random, string

                        rep = UserModel.objects.create(
                            username=f"fieldrep_{field_rep_id or gmail_id.split('@')[0]}",
                            email=gmail_id or f"{field_rep_id}@example.com",
                            field_id=field_rep_id or f"FR{random.randint(1000,9999)}",
                            role="field_rep",
                            password=make_password(
                                ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                            ),
                            is_active=True,
                        )

                        # ✅ MARK AS MANUALLY CREATED
                        if hasattr(rep, "created_by"):
                            rep.created_by = user_request
                            rep.save()

                        success_messages.append(f"Row {row_no}: Auto-created field rep {rep.field_id}")

                    created += 1
                    success_messages.append(f"Row {row_no}: Field rep {rep.field_id} validated")

                    # campaign assignment
                    if campaign:
                        CampaignAssignment.objects.get_or_create(field_rep=rep, campaign=campaign)
                        FieldRepCampaign.objects.get_or_create(field_rep=rep, campaign=campaign)

                except Exception as exc:
                    errors.append(f"Row {row_no}: {exc}")

        # ---------------- 6 COLUMN FORMAT ----------------
        elif is_6_col_format:
            file_obj.seek(0)
            reader = csv.DictReader(file_obj)

            for row_no, r in enumerate(reader, start=2):
                try:
                    rep_email = r.get("field_rep_email", "").strip()
                    doctor_name = r.get("doctor_name", "").strip()
                    doctor_contact = r.get("doctor_contact", "").strip()
                    col_id = r.get("collateral_id", "").strip()
                    share_channel = r.get("share_channel", "").strip() or "WhatsApp"
                    message_text = (r.get("message_text") or "").strip()

                    if not any([rep_email, doctor_name, doctor_contact]):
                        continue

                    rep = UserModel.objects.filter(role="field_rep", email__iexact=rep_email).first()
                    if not rep:
                        raise ValueError(f"Field rep {rep_email} not found")

                    col = None
                    if col_id:
                        col = Collateral.objects.get(id=int(col_id))

                    cutoff = timezone.now() - timedelta(hours=24)
                    if ShareLog.objects.filter(
                        field_rep=rep,
                        doctor_identifier=doctor_contact or doctor_name,
                        collateral=col,
                        share_channel=share_channel,
                        share_timestamp__gte=cutoff
                    ).exists():
                        continue

                    sl, _ = ShortLink.objects.get_or_create(
                        resource_type="collateral",
                        resource_id=col.id,
                        defaults=dict(
                            short_code=generate_short_code(),
                            is_active=True,
                            created_by=user_request,
                        ),
                    )

                    ShareLog.objects.create(
                        short_link=sl,
                        field_rep=rep,
                        doctor_identifier=doctor_contact or doctor_name,
                        share_channel=share_channel,
                        message_text=message_text,
                        collateral=col,
                        uploaded_by=user_request,   # ✅ THIS IS THE FIX
                    )

                    created += 1

                except Exception as exc:
                    errors.append(f"Row {row_no}: {exc}")

        else:
            errors.append("Invalid CSV format. Please use the provided template.")

        all_messages = success_messages + errors
        return created, all_messages, errors

# ─── Bulk *pre‑mapped* upload (new) ────────────────────────────────────────────
_whatsapp_re = re.compile(r"^\+?\d{8,15}$")   # very loose

logger = logging.getLogger(__name__)

_whatsapp_re = re.compile(r"^\+?\d{10,15}$")


class BulkPreMappedUploadForm(forms.Form):
    """
    CSV with header row:

    Doctor Name, Whatsapp Number, Field Rep ID (collateral_id optional)
    """

    csv_file = forms.FileField(
        label="Choose a CSV file",
        help_text="Columns: Doctor Name, Whatsapp Number, Field Rep ID (collateral_id optional)",
    )

    MAX_SIZE = 2 * 1024 * 1024  # 2 MB

    # 1️⃣ basic size & extension checks
    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("File larger than 2 MB.")
        if not f.name.lower().endswith(".csv"):
            raise ValidationError("Only .csv files are accepted.")
        return f

    # 2️⃣ helper – get / create doctor
    def _doctor_for_row(self, name: str, phone: str, rep: User) -> Doctor:
        obj, _ = Doctor.objects.get_or_create(
            rep=rep,
            phone=phone,
            defaults={"name": name.strip().title()},
        )
        return obj

    # 3️⃣ helper – create map + share-log
    def _create_link_and_sharelog(self, doctor, collateral, rep):
        from shortlink_management.models import ShortLink
        from shortlink_management.utils import generate_short_code

        DoctorCollateral.objects.get_or_create(
            doctor=doctor,
            collateral=collateral,
        )

        short = (
            ShortLink.objects.filter(
                resource_type="collateral",
                resource_id=collateral.id,
                is_active=True,
            ).first()
            or ShortLink.objects.create(
                short_code=generate_short_code(8),
                resource_type="collateral",
                resource_id=collateral.id,
                created_by=rep,
                is_active=True,
            )
        )

        return ShareLog.objects.create(
            short_link=short,
            field_rep=rep,
            doctor_identifier=doctor.phone,
            share_channel="WhatsApp",
            message_text="",
            collateral=collateral,
        )

    # 4️⃣ parse, validate & save
    def save(self, *, admin_user):
        """
        Returns (created_count, errors_list)
        """
        from collateral_management.models import Collateral

        created = 0
        errors = []

        try:
            content = self.cleaned_data["csv_file"].read().decode(
                "utf-8", errors="ignore"
            )
        except Exception as exc:
            return 0, [f"Failed to read CSV file: {exc}"]

        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []

        logger.debug("CSV columns detected: %s", fieldnames)

        doctor_name_col = whatsapp_col = fieldrep_id_col = collateral_id_col = None

        for col in fieldnames:
            col_l = col.lower().strip()

            if col == "Doctor Name":
                doctor_name_col = col
            elif col == "Whatsapp Number":
                whatsapp_col = col
            elif col == "Field Rep ID":
                fieldrep_id_col = col
            elif col_l in {"doctor_name", "doctor", "name"}:
                doctor_name_col = col
            elif col_l in {"whatsapp", "whatsapp number", "phone", "contact"}:
                whatsapp_col = col
            elif col_l in {"fieldrep_id", "field_rep_id", "field rep id"}:
                fieldrep_id_col = col
            elif col_l in {"collateral_id", "collateral"}:
                collateral_id_col = col

        missing = []
        if not doctor_name_col:
            missing.append("doctor_name")
        if not whatsapp_col:
            missing.append("whatsapp_number")
        if not fieldrep_id_col:
            missing.append("fieldrep_id")

        if missing:
            return 0, [
                f"Missing required columns: {', '.join(missing)}. "
                f"Found columns: {', '.join(fieldnames)}"
            ]

        for row_no, row in enumerate(reader, start=2):
            try:
                name = (row.get(doctor_name_col) or "").strip()
                phone_raw = (row.get(whatsapp_col) or "").strip()
                rep_id_raw = (row.get(fieldrep_id_col) or "").strip()
                collateral_raw = row.get(collateral_id_col)

                if not (name and phone_raw and rep_id_raw):
                    raise ValueError("Missing required column value")

                # Handle Excel scientific notation
                phone = phone_raw
                if "e" in phone.lower():
                    original = phone
                    phone = str(int(float(phone)))
                    logger.debug("Converted phone %s → %s", original, phone)

                phone = re.sub(r"[^\d+]", "", phone)

                if not _whatsapp_re.match(phone):
                    raise ValueError(f"Invalid WhatsApp number: {phone_raw}")

                # Resolve collateral
                if collateral_raw:
                    try:
                        collateral = Collateral.objects.get(id=int(collateral_raw))
                    except (ValueError, Collateral.DoesNotExist):
                        raise ValueError(f"Invalid collateral_id '{collateral_raw}'")
                else:
                    collateral = (
                        Collateral.objects.filter(is_active=True)
                        .order_by("-created_at")
                        .first()
                    )
                    if not collateral:
                        raise ValueError("No active collateral available")

                # Resolve field rep
                try:
                    rep = User.objects.get(pk=int(rep_id_raw), role="field_rep")
                except (ValueError, User.DoesNotExist):
                    try:
                        rep = User.objects.get(
                            field_id=rep_id_raw, role="field_rep"
                        )
                    except User.DoesNotExist:
                        raise ValueError(
                            f"Field Rep '{rep_id_raw}' not found"
                        )

                with transaction.atomic():
                    doctor = self._doctor_for_row(name, phone, rep)
                    self._create_link_and_sharelog(
                        doctor, collateral, rep
                    )

                created += 1

            except Exception as exc:
                errors.append(f"Line {row_no}: {exc}")

        return created, errors



# ─── Bulk *manual* – WhatsApp‑only ───────────────────────────────────────────
class BulkManualWhatsappShareForm(forms.Form):
    """
    CSV (<2 MB) with **two or three columns, no header**:

        field_rep_id, phone_number (doctor_name optional)
    """
    csv_file = forms.FileField(
        help_text=("CSV format: field_rep_id,phone_number (doctor_name optional)<br>"
                   "Or with headers: Field Rep ID,Field Rep Number<br>"
                   "Only field_rep_id and phone_number are required<br>"
                   "Example: FR22,+919876543210 or FR22,Dr. John,+919876543210"),
    )
    MAX_SIZE = 2 * 1024 * 1024  # 2 MB

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("CSV larger than 2 MB")
        return f

    def save(self, *, user_request):
        """
        Creates WhatsApp‑only ShareLog rows.
        Returns (created_cnt, errors[list]).
        """
        from django.contrib.auth import get_user_model
        from shortlink_management.models import ShortLink
        from shortlink_management.utils import generate_short_code
        from django.utils import timezone
        from datetime import timedelta

        data = self.cleaned_data["csv_file"].read().decode()
        file_obj = io.StringIO(data)

        # Auto-detect header
        peek = next(csv.reader(io.StringIO(data)), [])
        header_keys = {"field_rep_email", "doctor_name", "whatsapp_number", "field rep i", "field rep nur", "field rep id", "field rep number", "Field Rep ID", "Field Rep Number"}
        has_header = any((c or "").strip().lower() in header_keys for c in peek)

        created, errors = 0, []
        UserModel = get_user_model()

        if has_header:
            file_obj.seek(0)
            reader = csv.DictReader(file_obj)
            rows_iter = (
                (
                    r.get("field_rep_email", "") or r.get("field rep i", "") or r.get("field rep id", "") or r.get("Field Rep ID", ""),
                    r.get("doctor_name", "") or r.get("doctor", "") or r.get("name", ""),
                    r.get("whatsapp_number", "") or r.get("field rep nur", "") or r.get("field rep number", "") or r.get("Field Rep Number", "") or r.get("phone", ""),
                )
                for r in reader
            )
            start_row = 2  # header is row 1
        else:
            file_obj.seek(0)
            reader = csv.reader(file_obj)
            rows_iter = (
                tuple([c.strip() for c in (row + [""] * 3)[:3]])
                for row in reader if row and not row[0].strip().startswith("#")
            )
            start_row = 1

        for row_no, row in enumerate(rows_iter, start=start_row):
            try:
                # Ensure we have at least 2 columns (doctor_name is optional)
                if len(row) < 2:
                    raise ValueError(f"Row has only {len(row)} columns. Expected at least 2: field_rep_id, phone_number")
                
                # Pad row to 3 columns if doctor_name is missing
                row = list(row) + [""] * (3 - len(row))
                rep_email, doctor_name, phone_number = row
                
                # Validate required fields
                doctor_name = doctor_name.strip() if doctor_name else ""
                # If doctor name is empty, use field rep ID as doctor identifier
                if not doctor_name:
                    doctor_name = rep_email  # Use field rep ID as doctor name

                # field‑rep (accept both email and field rep ID)
                rep = None
                rep_email = rep_email.strip() if rep_email else ""
                
                if not rep_email:
                    raise ValueError("Field Rep email/ID cannot be empty")
                
                # Try multiple approaches to find the field rep
                search_attempts = [
                    # Exact email match
                    lambda: UserModel.objects.filter(email=rep_email, role="field_rep").first(),
                    # Case-insensitive email match
                    lambda: UserModel.objects.filter(email__iexact=rep_email, role="field_rep").first(),
                    # Exact field_id match
                    lambda: UserModel.objects.filter(field_id=rep_email, role="field_rep").first(),
                    # Case-insensitive field_id match
                    lambda: UserModel.objects.filter(field_id__iexact=rep_email, role="field_rep").first(),
                    # Partial field_id match
                    lambda: UserModel.objects.filter(field_id__icontains=rep_email, role="field_rep").first(),
                    # Username match
                    lambda: UserModel.objects.filter(username__iexact=rep_email, role="field_rep").first(),
                ]
                
                for attempt in search_attempts:
                    rep = attempt()
                    if rep:
                        break
                
                # Try numeric conversion for primary key
                if not rep:
                    try:
                        rep_id_numeric = int(rep_email)
                        rep = UserModel.objects.filter(pk=rep_id_numeric, role="field_rep").first()
                    except (ValueError, TypeError):
                        pass
                
                if not rep:
                    # AUTO-CREATE field rep if not found
                    try:
                        from django.contrib.auth.hashers import make_password
                        import string
                        import random
                        
                        # Generate a default password
                        default_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                        
                        # Determine if rep_email looks like an email or field ID
                        if '@' in rep_email:
                            # It's an email
                            email = rep_email
                            field_id = f"FR{random.randint(1000, 9999)}"
                            username = f'fieldrep_{rep_email.split("@")[0]}'
                        else:
                            # It's likely a field ID
                            field_id = rep_email
                            email = f'{rep_email}@example.com'
                            username = f'fieldrep_{rep_email.lower()}'
                        
                        # Create new field rep user
                        new_rep = UserModel.objects.create(
                            username=username,
                            email=email,
                            field_id=field_id,
                            role='field_rep',
                            password=make_password(default_password),
                            is_active=True
                        )
                        
                        rep = new_rep
                        print(f"DEBUG: Auto-created new field rep: {new_rep}")
                        
                    except Exception as create_error:
                        print(f"DEBUG: Failed to create field rep: {create_error}")
                        # Provide helpful error message with available field reps
                        available_reps = UserModel.objects.filter(role="field_rep").values_list('email', 'field_id', 'username')[:5]
                        if available_reps:
                            rep_list = ", ".join([f"{email} ({field_id or 'no ID'})" for email, field_id, username in available_reps])
                            raise ValueError(f"Field Rep with email or ID '{rep_email}' not found. Available field reps: {rep_list}")
                        else:
                            raise ValueError(f"Field Rep with email or ID '{rep_email}' not found. No field representatives exist in the system.")

                # Use the most recent active collateral as default
                col = Collateral.objects.filter(is_active=True).order_by('-created_at').first()
                if not col:
                    raise ValueError("No active collaterals found in system. Please create at least one active collateral first.")

                # quick phone sanity
                phone_number = phone_number.strip() if phone_number else ""
                if not phone_number:
                    raise ValueError("Phone number cannot be empty")
                
                # Handle scientific notation from Excel (e.g., 9.19812E+11)
                try:
                    if 'E' in phone_number.upper() or 'e' in phone_number:
                        # Convert scientific notation to regular number
                        phone_number = str(int(float(phone_number)))
                except:
                    pass  # If conversion fails, use original value
                
                digits = "".join(ch for ch in phone_number if ch.isdigit())
                if len(digits) < 8:
                    raise ValueError("phone_number looks too short")

                # Check for duplicate in last 24 hours
                cutoff_time = timezone.now() - timedelta(hours=24)
                duplicate_exists = ShareLog.objects.filter(
                    field_rep=rep,
                    doctor_identifier=digits,
                    collateral=col,
                    share_channel="WhatsApp",
                    share_timestamp__gte=cutoff_time
                ).exists()

                if duplicate_exists:
                    continue  # Skip duplicate

                # short‑link (create or reuse)
                sl, _ = ShortLink.objects.get_or_create(
                    resource_type="collateral",
                    resource_id=col.id,
                    defaults=dict(
                        short_code=generate_short_code(),
                        is_active=True,
                        created_by=user_request,
                    ),
                )

                ShareLog.objects.create(
                    short_link=sl,
                    field_rep=rep,
                    doctor_identifier=digits,
                    share_channel="WhatsApp",
                    message_text="",
                    collateral=col,
                )
                created += 1

            except Exception as exc:
                errors.append(f"Row {row_no}: {exc}")

        return created, errors

class BulkPreFilledWhatsappShareForm(forms.Form):
    """
    CSV with header: Doctor Name, Whatsapp Number, Field Rep ID (collateral_id, message_text optional)
    """
    csv_file = forms.FileField(
        label="Choose a CSV file",
        help_text="CSV must include Doctor Name, Whatsapp Number, Field Rep ID (collateral_id, message_text optional)",
    )

    MAX_SIZE = 2 * 1024 * 1024

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("File is too large.")
        if not f.name.lower().endswith(".csv"):
            raise ValidationError("Only CSV files allowed.")
        return f

    def save(self, *, admin_user) -> dict:
        """
        Returns:
            {
                "created": int,
                "errors": list[str],
                "logs": list[ShareLog],
            }
        """
        from django.contrib.auth import get_user_model
        from collateral_management.models import Collateral as CModel
        from shortlink_management.models import ShortLink
        from shortlink_management.utils import generate_short_code
        from django.utils import timezone
        from datetime import timedelta
        from django.conf import settings

        f = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader = csv.DictReader(f)
        
        stats = {"created": 0, "errors": [], "logs": []}
        UserModel = get_user_model()

        # Check required columns - only doctor_name, whatsapp_number, fieldrep_id are required
        required = {"doctor_name", "whatsapp_number", "fieldrep_id"}
        # Also accept your exact headers
        fieldnames_lower = {name.lower() for name in reader.fieldnames or []}
        if not {"doctor name", "whatsapp number", "field rep id"}.issubset(fieldnames_lower) and not required.issubset(fieldnames_lower):
            stats["errors"].append("CSV must include: Doctor Name, Whatsapp Number, Field Rep ID")
            return stats

        for row_no, row in enumerate(reader, start=2):  # header = row 1
            try:
                # Support both your headers and standard headers
                name = (row.get("doctor_name") or row.get("Doctor Name") or "").strip()
                phone = (row.get("whatsapp_number") or row.get("Whatsapp Number") or "").strip()
                rep_id = (row.get("fieldrep_id") or row.get("Field Rep ID") or "").strip()
                col_id = (row.get("collateral_id") or "").strip()
                message_text = (row.get("message_text") or "").strip()

                if not all([name, phone, rep_id]):
                    raise ValueError("Missing required column value")

                # Get field rep - handle both integer and string field_rep_id
                try:
                    # First try to find by field_id (which can be string like "FR1234")
                    rep = UserModel.objects.filter(role="field_rep", field_id=rep_id).first()
                    if not rep:
                        # If not found by field_id, try by username pattern
                        rep = UserModel.objects.filter(role="field_rep", username=f"field_rep_{rep_id}").first()
                    if not rep:
                        # Last resort: try if rep_id is a numeric user ID
                        try:
                            rep = UserModel.objects.get(id=int(rep_id), role="field_rep")
                        except (ValueError, UserModel.DoesNotExist):
                            pass
                    
                    if not rep:
                        raise ValueError(f"Unknown fieldrep_id «{rep_id}»")
                except Exception:
                    raise ValueError(f"Unknown fieldrep_id «{rep_id}»")

                # Get collateral (optional - use default if not provided)
                if col_id:
                    try:
                        col = CModel.objects.get(id=int(col_id), is_active=True)
                    except Exception:
                        raise ValueError(f"Unknown/Inactive collateral_id «{col_id}»")
                else:
                    # Use the most recent active collateral as default
                    col = CModel.objects.filter(is_active=True).order_by('-created_at').first()
                    if not col:
                        raise ValueError("No collateral_id provided and no active collaterals found in system.")

                # Clean phone number
                # Handle scientific notation from Excel (e.g., 9.19812E+11)
                try:
                    if 'E' in phone.upper() or 'e' in phone:
                        # Convert scientific notation to regular number
                        phone = str(int(float(phone)))
                except:
                    pass  # If conversion fails, use original value
                
                digits = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
                if len(digits) < 8:
                    raise ValueError("Invalid whatsapp_number")

                # Check for duplicate in last 24 hours
                cutoff_time = timezone.now() - timedelta(hours=24)
                duplicate_exists = ShareLog.objects.filter(
                    field_rep=rep,
                    doctor_identifier=digits,
                    collateral=col,
                    share_channel="WhatsApp",
                    share_timestamp__gte=cutoff_time
                ).exists()

                if duplicate_exists:
                    continue  # Skip duplicate

                # Create/find short link
                sl = ShortLink.objects.filter(
                    resource_type="collateral", resource_id=col.id, is_active=True
                ).first()
                if not sl:
                    sl = ShortLink.objects.create(
                        resource_type="collateral",
                        resource_id=col.id,
                        short_code=generate_short_code(length=8),
                        is_active=True,
                        created_by=admin_user if getattr(admin_user, "is_authenticated", False) else None,
                    )

                # Create ShareLog
                share_log = ShareLog.objects.create(
                    short_link=sl,
                    field_rep=rep,
                    doctor_identifier=digits,
                    share_channel="WhatsApp",
                    message_text=message_text,
                    collateral=col,
                )
                
                stats["logs"].append(share_log)
                stats["created"] += 1

            except Exception as e:
                msg = f"Row {row_no}: {e}"
                stats["errors"].append(msg)

        return stats
class BulkPreMappedByLoginForm(forms.Form):
    """
    Pre-register doctor ↔ collateral without sending via WhatsApp/SMS/Email.
    CSV with REQUIRED header: Doctor Name, Gmail ID, Field Rep ID (collateral_id optional)
    """
    csv_file = forms.FileField(
        help_text="CSV with header: Doctor Name,Gmail ID,Field Rep ID (collateral_id optional)"
    )
    MAX_SIZE = 2 * 1024 * 1024  # 2 MB

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("CSV larger than 2 MB")
        return f

    def _digits(self, s: str) -> str:
        return "".join(ch for ch in (s or "") if ch.isdigit() or ch == "+")

    def _doctor_for_row(self, rep, name: str, phone: str):
        digits = self._digits(phone)
        if not digits:
            raise ValueError("Missing/invalid whatsapp_number")
        doc, created = Doctor.objects.get_or_create(
            rep=rep, phone=digits,
            defaults={"name": name or digits, "source": "manual"}
        )
        # keep name updated if newly provided
        if not created and name and doc.name != name:
            doc.name = name
            doc.save(update_fields=["name"])
        return doc, created

    def save(self, *, admin_user):
        import io
        from django.contrib.auth import get_user_model
        from collateral_management.models import Collateral as CModel  # to avoid name clash
        from shortlink_management.models import ShortLink
        from shortlink_management.utils import generate_short_code
        from django.conf import settings

        file_obj = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader = csv.DictReader(file_obj)

        created_doctors = 0
        created_or_existing_links = 0
        updated_mappings = 0
        errors, rows = [], []

        UserModel = get_user_model()

        for row_no, row in enumerate(reader, start=2):  # header = row 1
            try:
                # Support both your headers and standard headers
                name   = (row.get("doctor_name") or row.get("Doctor Name") or "").strip()
                email  = (row.get("gmail_id") or row.get("Gmail ID") or "").strip()
                phone  = (row.get("whatsapp_number") or "").strip()
                rep_id = (row.get("fieldrep_id") or row.get("Field Rep ID") or "").strip()
                col_id = (row.get("collateral_id") or "").strip()

                if not rep_id:
                    raise ValueError("Field Rep ID is required")
                
                # Use email as primary contact, phone as fallback
                primary_contact = email if email else phone

                # field rep - handle both integer and string field_rep_id
                try:
                    # First try to find by field_id (which can be string like "FR1234")
                    rep = UserModel.objects.filter(role="field_rep", field_id=rep_id).first()
                    if not rep:
                        # If not found by field_id, try by username pattern
                        rep = UserModel.objects.filter(role="field_rep", username=f"field_rep_{rep_id}").first()
                    if not rep:
                        # Last resort: try if rep_id is a numeric user ID
                        try:
                            rep = UserModel.objects.get(id=int(rep_id), role="field_rep")
                        except (ValueError, UserModel.DoesNotExist):
                            pass
                    
                    if not rep:
                        raise ValueError(f"Unknown fieldrep_id «{rep_id}»")
                except Exception:
                    raise ValueError(f"Unknown fieldrep_id «{rep_id}»")

                # collateral (optional - use default if not provided)
                if col_id:
                    try:
                        col = CModel.objects.get(id=int(col_id), is_active=True)
                    except Exception:
                        raise ValueError(f"Unknown/Inactive collateral_id «{col_id}»")
                else:
                    # Use the most recent active collateral as default
                    col = CModel.objects.filter(is_active=True).order_by('-created_at').first()
                    if not col:
                        raise ValueError("No collateral_id provided and no active collaterals found in system.")

                # doctor - use email as primary contact, phone as fallback
                doctor, d_created = self._doctor_for_row(rep, name, primary_contact)
                if d_created:
                    created_doctors += 1

                # mapping
                dc, mapping_created = DoctorCollateral.objects.get_or_create(
                    doctor=doctor, collateral=col
                )
                if mapping_created:
                    updated_mappings += 1

                # short link (one-per-collateral)
                sl = ShortLink.objects.filter(
                    resource_type="collateral", resource_id=col.id, is_active=True
                ).first()
                if not sl:
                    sl = ShortLink.objects.create(
                        resource_type="collateral",
                        resource_id=col.id,
                        short_code=generate_short_code(length=8),
                        is_active=True,
                        created_by=admin_user if getattr(admin_user, "is_authenticated", False) else None,
                    )
                created_or_existing_links += 1

                # Generate short URL using request context or fallback
                try:
                    from django.urls import reverse
                    short_url = reverse('resolve_shortlink', args=[sl.short_code])
                except:
                    # Fallback to relative URL if reverse fails
                    short_url = f"/view/{sl.short_code}"
                rows.append({
                    "row": row_no,
                    "doctor": f"{doctor.name} ({doctor.phone})",
                    "short_url": short_url,
                    "error": "",
                })
            except Exception as e:
                msg = f"Row {row_no}: {e}"
                errors.append(msg)
                rows.append({"row": row_no, "doctor": "", "short_url": "", "error": str(e)})

        return {
            "created": created_doctors,
            "updated": updated_mappings,
            "errors": errors,
            "rows": rows,
        }


class CollateralForm(forms.ModelForm):
    class Meta:
        model = Collateral
        fields = [
            'title',
            'type',
            'purpose',
            'file',
            'vimeo_url',
            'content_id',
            'banner_1',
            'banner_2',
            'description',
            'is_active'
        ]
