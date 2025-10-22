import csv, io, re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.text import slugify
from user_management.models import User
from doctor_viewer.models import Doctor, DoctorCollateral
from collateral_management.models import Collateral
from .models import ShareLog

# ─── Common constants ──────────────────────────────────────────────────────────
CHANNEL_CHOICES = (
    ("WhatsApp", "WhatsApp"),
    ("SMS",      "SMS"),
    ("Email",    "Email"),
)

# ─── One‑off share form ────────────────────────────────────────────────────────
class ShareForm(forms.Form):
    collateral = forms.ModelChoiceField(
        queryset=Collateral.objects.filter(is_active=True),
        label="Select Collateral",
    )
    doctor_contact = forms.CharField(
        max_length=255,
        label="Phone / E‑mail",
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

        # Bootstrap 5 classes
        self.fields["collateral"].widget.attrs.update({"class": "form-select"})
        self.fields["doctor_contact"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "+91XXXXXXXXXX or doctor@example.com",
        })
        self.fields["share_channel"].widget.attrs.update({"class": "form-select"})
        self.fields["message_text"].widget.attrs.update({
            "class": "form-control",
            "rows": "4",
            "placeholder": "Write a message (optional)",
        })

    # ── validation ────────────────────────────────────────────────────────────
    def clean(self):
        cleaned = super().clean()
        channel = cleaned.get("share_channel")
        contact = (cleaned.get("doctor_contact") or "").strip()

        if not contact:
            raise ValidationError("Please enter the recipient’s phone or e‑mail.")

        if channel == "Email":
            try:
                validate_email(contact)
            except ValidationError:
                raise ValidationError("Enter a valid e‑mail address.")
        else:
            digits = "".join(ch for ch in contact if ch.isdigit() or ch == "+")
            if len(digits) < 8:
                raise ValidationError("Enter a valid phone number.")
            cleaned["doctor_contact"] = digits

        return cleaned


# ─── Bulk *manual* share (existing) ────────────────────────────────────────────
class BulkManualShareForm(forms.Form):
    """
    Expects a small CSV (< 2 MB) with six columns **without** a header row:

      field_rep_email, doctor_name, doctor_contact, collateral_id,
      share_channel (WhatsApp/SMS/Email), message_text(optional)
    """
    csv_file = forms.FileField(
        help_text=("CSV: field_rep_email,doctor_name,doctor_contact,"
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
        from shortlink_management.models import ShortLink
        from shortlink_management.utils import generate_short_code
        from django.utils import timezone
        from datetime import timedelta

        data = self.cleaned_data["csv_file"].read().decode()
        file_obj = io.StringIO(data)

        # Auto-detect header
        peek = next(csv.reader(io.StringIO(data)), [])
        header_keys = {"field_rep_email", "doctor_name", "doctor_contact", "collateral_id", "share_channel", "message_text"}
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
                    r.get("doctor_contact", "").strip(),
                    r.get("collateral_id", "").strip(),
                    r.get("share_channel", "").strip(),
                    (r.get("message_text") or "").strip(),
                )
                for r in reader
            )
            start_row = 2  # header is row 1
        else:
            file_obj.seek(0)
            reader = csv.reader(file_obj)
            rows_iter = (
                tuple([c.strip() for c in (row + [""] * 6)[:6]])
                for row in reader if row and not row[0].strip().startswith("#")
            )
            start_row = 1

        for row_no, row in enumerate(rows_iter, start=start_row):
            try:
                rep_email, doctor_name, doctor_contact, col_id, share_channel, message_text = row

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

                # phone / e‑mail quick check
                if share_channel == "Email":
                    validate_email(doctor_contact)
                else:
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
                rep_id =  int(row.get("fieldrep_id") or 0)
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

                # Get field rep
                try:
                    rep = UserModel.objects.get(id=int(rep_id), role="field_rep")
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

                # field rep
                try:
                    rep = UserModel.objects.get(id=int(rep_id), role="field_rep")
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
