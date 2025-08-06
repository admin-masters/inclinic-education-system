import csv, io, re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from user_management.models import User  # custom user
from doctor_viewer.models import Doctor

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

    def clean_csv_file(self):
        f = self.cleaned_data['csv_file']
        if f.size > 2*1024*1024:
            raise ValidationError("CSV larger than 2 MB.")
        return f

    def save(self, admin_user):
        """
        Returns (created_count, updated_count, errors[list]).
        """
        file_obj = io.StringIO(self.cleaned_data['csv_file'].read().decode())
        reader = csv.reader(file_obj)
        created = updated = 0
        errors = []

        for row_num, row in enumerate(reader, start=1):
            if not row or row[0].strip().lower() in ('name', ''):
                continue  # skip header/blank
            try:
                name, email, phone = [c.strip() for c in row]
                if not PHONE_RE_CSV.match(phone):
                    raise ValueError("Bad phone format")
                obj, is_new = User.objects.update_or_create(
                    email=email,
                    defaults={
                        'username': email.split('@')[0],
                        'name': name,
                        'phone': phone,
                        'role': 'field_rep',
                        'active': True,
                    }
                )
                created += 1 if is_new else 0
                updated += 0 if is_new else 1
            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")

        return created, updated, errors

# ------------------------------------------------------------------
# SINGLE FIELD-REP FORM (email · phone · field_id)
# ------------------------------------------------------------------
PHONE_RE = RegexValidator(r'^\+?\d{7,15}$')

class FieldRepForm(forms.ModelForm):
    phone_number = forms.CharField(
        validators=[PHONE_RE],
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "+919876543210"
        }),
        label="Field Rep Number"
    )

    class Meta:
        model = User
        fields = ("email", "phone_number", "field_id")
        labels = {
            "email": "Gmail ID",
            "field_id": "Field ID",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "field_id": forms.TextInput(attrs={"class": "form-control"}),
        }

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
