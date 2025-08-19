import csv, io, re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.text import slugify
from user_management.models import User
from doctor_viewer.models import Doctor, DoctorCollateral
from collateral_management.models import Collateral
from .models import ShareLog
from collateral_management.models import Collateral

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
        file_obj = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader   = csv.reader(file_obj)
        created, errors = 0, []

        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        from shortlink_management.models import ShortLink

        for row_no, row in enumerate(reader, start=1):
            if not row or row[0].strip().startswith("#"):
                continue  # skip blank / commented rows
            try:
                (
                    rep_email, doctor_name, doctor_contact,
                    col_id, share_channel, message_text,
                ) = [c.strip() for c in (row + [""] * 6)[:6]]

                # field rep
                try:
                    rep = UserModel.objects.get(email=rep_email, role="field_rep")
                except UserModel.DoesNotExist:
                    raise ValueError(f"Unknown field‑rep e‑mail «{rep_email}»")

                # collateral
                try:
                    col = Collateral.objects.get(id=int(col_id), is_active=True)
                except Collateral.DoesNotExist:
                    raise ValueError(f"Invalid / inactive collateral_id «{col_id}»")

                # phone / e‑mail quick check
                if share_channel == "Email":
                    validate_email(doctor_contact)
                else:
                    digits = "".join(ch for ch in doctor_contact if ch.isdigit())
                    if len(digits) < 8:
                        raise ValueError("doctor_contact looks too short")

                # short‑link (create or reuse)
                sl, _ = ShortLink.objects.get_or_create(
                    resource_type="collateral",
                    resource_id=col.id,
                    defaults=dict(
                        short_code=ShortLink.generate_unique_code(),
                        is_active=True,
                        created_by=user_request,
                    ),
                )

                ShareLog.objects.create(
                    short_link        = sl,
                    field_rep         = rep,
                    doctor_identifier = doctor_contact or doctor_name,
                    share_channel     = share_channel or "WhatsApp",
                    message_text      = message_text,
                )
                created += 1

            except Exception as exc:        # noqa: BLE001
                errors.append(f"Row {row_no}: {exc}")

        return created, errors


# ─── Bulk *pre‑mapped* upload (new) ────────────────────────────────────────────
_whatsapp_re = re.compile(r"^\+?\d{8,15}$")   # very loose

class BulkPreMappedUploadForm(forms.Form):
    """
    CSV with **header row**:

      doctor_name, whatsapp_number, fieldrep_id
    """
    csv_file = forms.FileField(
        label="Choose a CSV file",
        help_text="Columns: doctor_name, whatsapp_number, fieldrep_id",
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
        )

    # 4️⃣ parse, validate & save -----------------------------------------------
    def save(self, collateral: Collateral, *, admin_user) -> dict:
        """
        Returns summary:

          {
            "created": int,
            "updated": int,
            "errors":  [str],
            "logs":    [ShareLog],
          }
        """
        f      = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader = csv.DictReader(f)
        stats  = {"created": 0, "updated": 0, "errors": [], "logs": []}

        for row_no, row in enumerate(reader, start=2):   # header = line 1
            try:
                name   = (row.get("doctor_name")     or "").strip()
                phone  = (row.get("whatsapp_number") or "").strip()
                rep_id =  int(row.get("fieldrep_id") or 0)

                if not (name and phone and rep_id):
                    raise ValueError("Missing required column value")
                if not _whatsapp_re.match(phone):
                    raise ValueError("Bad phone format")

                rep = User.objects.get(pk=rep_id, role="field_rep")
                doc = self._doctor_for_row(name, phone, rep)
                log = self._create_link_and_sharelog(doc, collateral, rep)

                stats["logs"].append(log)
                stats["created"] += 1

            except Exception as exc:                     # noqa: BLE001
                stats["errors"].append(f"Line {row_no}: {exc}")

        return stats
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
        file_obj = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader   = csv.reader(file_obj)
        created, errors = 0, []

        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        from shortlink_management.models import ShortLink

        for row_no, row in enumerate(reader, start=1):
            if not row or row[0].strip().startswith("#"):
                continue
            try:
                (
                    rep_email, doctor_name, phone_number,
                    col_id,   message_text,
                ) = [c.strip() for c in (row + [""] * 5)[:5]]

                # field‑rep
                rep = UserModel.objects.get(email=rep_email, role="field_rep")

                # collateral
                col = Collateral.objects.get(id=int(col_id), is_active=True)

                # quick phone sanity
                digits = "".join(ch for ch in phone_number if ch.isdigit())
                if len(digits) < 8:
                    raise ValueError("phone_number looks too short")

                # short‑link (create or reuse)
                sl, _ = ShortLink.objects.get_or_create(
                    resource_type="collateral",
                    resource_id=col.id,
                    defaults=dict(
                        short_code=ShortLink.generate_unique_code(),
                        is_active=True,
                        created_by=user_request,
                    ),
                )

                ShareLog.objects.create(
                    short_link        = sl,
                    field_rep         = rep,
                    doctor_identifier = digits,
                    share_channel     = "WhatsApp",
                    message_text      = message_text,
                )
                created += 1

            except Exception as exc:
                errors.append(f"Row {row_no}: {exc}")

        return created, errors

class BulkPreFilledWhatsappShareForm(forms.Form):
    """
    CSV with header: doctor_name, whatsapp_number, fieldrep_id
    """
    csv_file = forms.FileField(
        label="Choose a CSV file",
        help_text="CSV must include doctor_name, whatsapp_number, fieldrep_id",
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
        f = io.StringIO(self.cleaned_data["csv_file"].read().decode())
        reader = csv.DictReader(f)
        
        # Note: Collateral field removed - this method needs to be updated
        # to handle the business logic without collateral selection
        
        stats = {"created": 0, "errors": [], "logs": []}
        
        # For now, return an error indicating this needs to be configured
        stats["errors"].append("This functionality needs to be configured for operation without collateral selection")
        
        return stats
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
