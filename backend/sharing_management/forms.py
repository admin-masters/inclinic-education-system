import csv, io, re
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
        super().__init__(*args, **kwargs)
        self.user = user
        
        # Set initial collateral to the most recent one
        latest_collateral = Collateral.objects.filter(is_active=True).order_by('-created_at').first()
        if latest_collateral:
            self.fields['collateral'].initial = latest_collateral
        
        # Update doctor queryset to show only assigned doctors
        self.fields['existing_doctor'].queryset = self.get_doctors_with_status()
    
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
        
        # Check if either existing doctor or new doctor info is provided
        existing_doctor = cleaned_data.get('existing_doctor')
        new_doctor_name = cleaned_data.get('new_doctor_name')
        doctor_contact = cleaned_data.get('doctor_contact')
        
        if not existing_doctor and not (new_doctor_name and doctor_contact):
            raise ValidationError("Please select an existing doctor or enter new doctor details.")
        
        if existing_doctor and (new_doctor_name or doctor_contact):
            raise ValidationError("Please either select an existing doctor OR enter new doctor details, not both.")
        
        # Validate contact if new doctor
        if new_doctor_name and doctor_contact:
            if not doctor_contact.strip():
                raise ValidationError("Please enter a contact number for the new doctor.")
            
            # Basic phone validation
            digits = "".join(ch for ch in doctor_contact if ch.isdigit() or ch == "+")
            if len(digits) < 8:
                raise ValidationError("Please enter a valid phone number.")
            
            cleaned_data['doctor_contact'] = digits


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

    MAX_SIZE = 2 * 1024 * 1024       # 2 MB

    # 1️⃣ basic size check ------------------------------------------------------
    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("CSV larger than 2 MB")
        return f

    # 2️⃣ parse & validate ------------------------------------------------------
    def save(self, *, user_request):
        """
        Reads the file, creates `ShareLog` rows,
        returns tuple (created_count, errors[list]).
        """
        from django.contrib.auth import get_user_model
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from datetime import timedelta

        data = self.cleaned_data["csv_file"].read().decode()
        file_obj = io.StringIO(data)

        # Auto-detect header and format
        peek = next(csv.reader(io.StringIO(data)), [])
        header_keys_2 = {"field rep id", "gmail id", "field_rep_id", "gmail_id"}
        header_keys_6 = {"field_rep_email", "doctor_name", "doctor_contact", "collateral_id", "share_channel", "message_text"}
        
        # Detect format
        is_2_col_format = any((c or "").strip().lower() in header_keys_2 for c in peek[:2])
        is_6_col_format = any((c or "").strip().lower() in header_keys_6 for c in peek)
        
        created, errors = 0, []
        UserModel = get_user_model()

        if is_2_col_format:
            # Handle 2-column format: Field Rep ID, Gmail ID
            file_obj.seek(0)
            reader = csv.DictReader(file_obj)
            rows_iter = (
                (
                    r.get("Field Rep ID", "").strip() or r.get("field_rep_id", "").strip(),
                    r.get("Gmail ID", "").strip() or r.get("gmail_id", "").strip(),
                )
                for r in reader
            )
            start_row = 2  # header is row 1
            
            for row_no, (field_rep_id, gmail_id) in enumerate(rows_iter, start=start_row):
                try:
                    # Skip empty rows
                    if not field_rep_id and not gmail_id:
                        continue
                    
                    # For 2-column format, we're just validating the field reps exist
                    # No actual sharing is performed
                    if field_rep_id:
                        # Check if field rep exists by field_id
                        rep = UserModel.objects.filter(role="field_rep", field_id=field_rep_id).first()
                        if not rep:
                            # Try by email
                            rep = UserModel.objects.filter(role="field_rep", email=gmail_id).first()
                            if not rep:
                                errors.append(f"Row {row_no}: Field Rep with ID '{field_rep_id}' or email '{gmail_id}' not found")
                                continue
                    elif gmail_id:
                        # Check by email
                        rep = UserModel.objects.filter(role="field_rep", email=gmail_id).first()
                        if not rep:
                            errors.append(f"Row {row_no}: Field Rep with email '{gmail_id}' not found")
                            continue
                    
                    created += 1
                    
                except Exception as exc:
                    errors.append(f"Row {row_no}: {exc}")
        
        elif is_6_col_format:
            # Handle original 6-column format
            file_obj.seek(0)
            reader = csv.DictReader(file_obj)
            rows_iter = (
                (
                    r.get("field_rep_email", "").strip(),
                    r.get("doctor_name", "").strip(),
                    r.get("doctor_contact", "").strip(),
                    r.get("collateral_id", "").strip(),
                    r.get("share_channel", "").strip(),
                    (r.get("message_text") or "").strip(),
                )
                for r in reader
            )
            start_row = 2  # header is row 1

            for row_no, row in enumerate(rows_iter, start=start_row):
                try:
                    rep_email, doctor_name, doctor_contact, col_id, share_channel, message_text = row

                    # Skip empty rows
                    if not any(row):
                        continue

                    # field rep
                    try:
                        rep = UserModel.objects.get(email=rep_email, role="field_rep")
                    except UserModel.DoesNotExist:
                        # Try to find any field rep or use current user as fallback
                        rep = UserModel.objects.filter(role="field_rep").first()
                        if not rep:
                            rep = user_request
                        if not rep:
                            raise ValueError(f"No field representatives available in system")

                    # collateral
                    if col_id:
                        try:
                            col = Collateral.objects.get(id=int(col_id))
                        except Collateral.DoesNotExist:
                            # Check if it exists in the other Collateral model
                            from campaign_management.models import Collateral as CampaignCollateral
                            try:
                                campaign_col = CampaignCollateral.objects.get(id=int(col_id))
                                raise ValueError(f"Invalid collateral_id «{col_id}». This ID exists in Campaign Management but not in Collateral Management. Please use a collateral from the Collateral Management system.")
                            except CampaignCollateral.DoesNotExist:
                                pass
                            
                            # Provide helpful error with available IDs
                            available_ids = list(Collateral.objects.filter(is_active=True).values_list('id', flat=True)[:10])
                            if available_ids:
                                raise ValueError(f"Invalid collateral_id «{col_id}». Available active IDs: {available_ids}")
                            else:
                                raise ValueError(f"Invalid collateral_id «{col_id}». No active collaterals found in database.")
                    else:
                        col = None

                    # phone / e‑mail quick check
                    if col and share_channel == "Email":
                        validate_email(doctor_contact)
                    elif col:
                        # Handle scientific notation from Excel (e.g., 9.19812E+11)
                        try:
                            if 'E' in doctor_contact.upper() or 'e' in doctor_contact:
                                # Convert scientific notation to regular number
                                doctor_contact = str(int(float(doctor_contact)))
                        except:
                            pass  # If conversion fails, use original value
                        
                        digits = "".join(ch for ch in doctor_contact if ch.isdigit())
                        if len(digits) < 8:
                            raise ValueError("doctor_contact looks too short")

                    # If we have a collateral, create share log
                    if col:
                        # Check for duplicate in last 24 hours
                        cutoff_time = timezone.now() - timedelta(hours=24)
                        duplicate_exists = ShareLog.objects.filter(
                            field_rep=rep,
                            doctor_identifier=doctor_contact or doctor_name,
                            collateral=col,
                            share_channel=share_channel or "WhatsApp",
                            share_timestamp__gte=cutoff_time
                        ).exists()

                        if duplicate_exists:
                            continue  # Skip duplicate

                        # short‑link (create or reuse)
                        from shortlink_management.models import ShortLink
                        from shortlink_management.utils import generate_short_code
                        
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
                            share_channel=share_channel or "WhatsApp",
                            message_text=message_text,
                            collateral=col,
                        )
                    created += 1

                except Exception as exc:        # noqa: BLE001
                    errors.append(f"Row {row_no}: {exc}")
        else:
            # Unknown format
            errors.append("Invalid CSV format. Please use either 2-column format (Field Rep ID, Gmail ID) or 6-column format (field_rep_email, doctor_name, doctor_contact, collateral_id, share_channel, message_text)")

        return created, errors


# ─── Bulk *pre‑mapped* upload (new) ────────────────────────────────────────────
_whatsapp_re = re.compile(r"^\+?\d{8,15}$")   # very loose

class BulkPreMappedUploadForm(forms.Form):
    """
    CSV with **header row**:

      doctor_name, whatsapp_number, fieldrep_id, collateral_id
    """
    csv_file = forms.FileField(
        label="Choose a CSV file",
        help_text="Columns: doctor_name, whatsapp_number, fieldrep_id, collateral_id",
    )

    # 1️⃣ basic size & extension checks ----------------------------------------
    MAX_SIZE = 2 * 1024 * 1024  # 2 MB

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if f.size > self.MAX_SIZE:
            raise ValidationError("File larger than 2 MB.")
        if not f.name.lower().endswith(".csv"):
            raise ValidationError("Only .csv files are accepted.")
        return f

    # 2️⃣ helper – get / create doctor -----------------------------------------
    def _doctor_for_row(self, name: str, phone: str, rep: User) -> Doctor:
        obj, _ = Doctor.objects.get_or_create(
            rep=rep,
            phone=phone,
            defaults={"name": name.strip().title()},
        )
        return obj

    # 3️⃣ helper – create map + share‑log --------------------------------------
    def _create_link_and_sharelog(
        self, doctor: Doctor, collateral: Collateral, rep: User
    ) -> ShareLog:
        # link doctor ↔ collateral
        DoctorCollateral.objects.get_or_create(
            doctor=doctor,
            collateral=collateral,
        )

        # find / create short‑link
        from shortlink_management.models import ShortLink
        from shortlink_management.utils  import generate_short_code

        short = (
            ShortLink.objects
            .filter(resource_type="collateral",
                    resource_id=collateral.id, is_active=True)
            .first()
            or ShortLink.objects.create(
                short_code   = generate_short_code(8),
                resource_type= "collateral",
                resource_id  = collateral.id,
                created_by   = rep,
                is_active    = True,
            )
        )

        # share‑log row
        return ShareLog.objects.create(
            short_link        = short,
            field_rep         = rep,
            doctor_identifier = doctor.phone,
            share_channel     = "WhatsApp",
            message_text      = "",   # user may edit later
            collateral        = collateral,
        )

    # 4️⃣ parse, validate & save -----------------------------------------------
    def save(self, *, admin_user) -> tuple:
        """
        Returns (created_count, errors_list)
        """
        from collateral_management.models import Collateral
        
        f      = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader = csv.DictReader(f)
        created = 0
        errors = []
        
        # Check required columns
        required = {"doctor_name", "whatsapp_number", "fieldrep_id", "collateral_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            errors.append(f"Missing columns: {', '.join(sorted(missing))}")
            return 0, errors

        for row_no, row in enumerate(reader, start=2):   # header = line 1
            try:
                name   = (row.get("doctor_name")     or "").strip()
                phone  = (row.get("whatsapp_number") or "").strip()
                rep_id = (row.get("fieldrep_id") or "").strip()
                collateral_id = int(row.get("collateral_id") or 0)

                if not (name and phone and rep_id and collateral_id):
                    raise ValueError("Missing required column value")
                if not _whatsapp_re.match(phone):
                    raise ValueError("Bad phone format")

                # Get collateral and field rep
                collateral = Collateral.objects.get(id=collateral_id)
                rep = User.objects.get(pk=rep_id, role="field_rep")
                doc = self._doctor_for_row(name, phone, rep)
                log = self._create_link_and_sharelog(doc, collateral, rep)

                created += 1

            except Exception as exc:                     # noqa: BLE001
                errors.append(f"Line {row_no}: {exc}")

        return created, errors


# ─── Bulk *manual* – WhatsApp‑only ───────────────────────────────────────────
class BulkManualWhatsappShareForm(forms.Form):
    """
    CSV (<2 MB) with **five columns, no header**:

        field_rep_email, doctor_name, phone_number, collateral_id, message_text(optional)
    """
    csv_file = forms.FileField(
        help_text=("CSV: field_rep_email,doctor_name,phone_number,"
                   "collateral_id,message_text"),
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
        header_keys = {"field_rep_email", "doctor_name", "whatsapp_number", "collateral_id", "message_text"}
        has_header = any((c or "").strip().lower() in header_keys for c in peek)

        created, errors = 0, []
        UserModel = get_user_model()

        if has_header:
            file_obj.seek(0)
            reader = csv.DictReader(file_obj)
            rows_iter = (
                (
                    r.get("field_rep_email", "").strip(),
                    r.get("doctor_name", "").strip(),
                    r.get("whatsapp_number", "").strip(),
                    r.get("collateral_id", "").strip(),
                    (r.get("message_text") or "").strip(),
                )
                for r in reader
            )
            start_row = 2  # header is row 1
        else:
            file_obj.seek(0)
            reader = csv.reader(file_obj)
            rows_iter = (
                tuple([c.strip() for c in (row + [""] * 5)[:5]])
                for row in reader if row and not row[0].strip().startswith("#")
            )
            start_row = 1

        for row_no, row in enumerate(rows_iter, start=start_row):
            try:
                rep_email, doctor_name, phone_number, col_id, message_text = row

                # field‑rep
                rep = UserModel.objects.get(email=rep_email, role="field_rep")

                # collateral
                try:
                    col = Collateral.objects.get(id=int(col_id))
                except Collateral.DoesNotExist:
                    # Check if it exists in the other Collateral model
                    from campaign_management.models import Collateral as CampaignCollateral
                    try:
                        campaign_col = CampaignCollateral.objects.get(id=int(col_id))
                        raise ValueError(f"Invalid collateral_id «{col_id}». This ID exists in Campaign Management but not in Collateral Management. Please use a collateral from the Collateral Management system.")
                    except CampaignCollateral.DoesNotExist:
                        pass
                    
                    # Provide helpful error with available IDs
                    available_ids = list(Collateral.objects.filter(is_active=True).values_list('id', flat=True)[:10])
                    if available_ids:
                        raise ValueError(f"Invalid collateral_id «{col_id}». Available active IDs: {available_ids}")
                    else:
                        raise ValueError(f"Invalid collateral_id «{col_id}». No active collaterals found in database.")

                # quick phone sanity
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
                    message_text=message_text,
                    collateral=col,
                )
                created += 1

            except Exception as exc:
                errors.append(f"Row {row_no}: {exc}")

        return created, errors

class BulkPreFilledWhatsappShareForm(forms.Form):
    """
    CSV with header: doctor_name, whatsapp_number, fieldrep_id, collateral_id, message_text
    """
    csv_file = forms.FileField(
        label="Choose a CSV file",
        help_text="CSV must include doctor_name, whatsapp_number, fieldrep_id, collateral_id, message_text",
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

        # Check required columns
        required = {"doctor_name", "whatsapp_number", "fieldrep_id", "collateral_id", "message_text"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            stats["errors"].append(f"Missing columns: {', '.join(sorted(missing))}")
            return stats

        for row_no, row in enumerate(reader, start=2):  # header = row 1
            try:
                name = (row.get("doctor_name") or "").strip()
                phone = (row.get("whatsapp_number") or "").strip()
                rep_id = (row.get("fieldrep_id") or "").strip()
                col_id = (row.get("collateral_id") or "").strip()
                message_text = (row.get("message_text") or "").strip()

                if not all([name, phone, rep_id, col_id]):
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

                # Get collateral
                try:
                    col = CModel.objects.get(id=int(col_id), is_active=True)
                except Exception:
                    raise ValueError(f"Unknown/Inactive collateral_id «{col_id}»")

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
    CSV with REQUIRED header: doctor_name, whatsapp_number, fieldrep_id, collateral_id
    """
    csv_file = forms.FileField(
        help_text="CSV with header: doctor_name,whatsapp_number,fieldrep_id,collateral_id"
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
                name   = (row.get("doctor_name") or "").strip()
                phone  = (row.get("whatsapp_number") or "").strip()
                rep_id = (row.get("fieldrep_id") or "").strip()
                col_id = (row.get("collateral_id") or "").strip()

                if not rep_id or not col_id:
                    raise ValueError("fieldrep_id and collateral_id are required")

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

                # collateral
                try:
                    col = CModel.objects.get(id=int(col_id), is_active=True)
                except Exception:
                    raise ValueError(f"Unknown/Inactive collateral_id «{col_id}»")

                # doctor
                doctor, d_created = self._doctor_for_row(rep, name, phone)
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

                short_url = f"{settings.SITE_BASE_URL}/view/{sl.short_code}"
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
