import csv, io, re
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from user_management.models import User  # custom user
from doctor_viewer.models import Doctor
from campaign_management.models import Campaign, CampaignAssignment
from admin_dashboard.models import FieldRepCampaign

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
    
    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Set role to field_rep
        user.role = 'field_rep'
        
        # Generate username from email if not set
        if not user.username:
            base_username = user.email.split('@')[0]
            username = base_username
            counter = 1
            
            # Ensure username is unique
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
