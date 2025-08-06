from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator


class SecurityQuestion(models.Model):
    """
    One row per question chosen by Inditech; keep them in a lookup so you can A/B test phrasings later.
    """
    question = models.CharField(max_length=255, unique=True)
    
    def __str__(self):
        return self.question


class UserSecurityAnswer(models.Model):
    """
    Stores the hash of the answer a Field-Rep gave during registration.
    """
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='security_answers'
    )
    question = models.ForeignKey(
        SecurityQuestion,
        on_delete=models.CASCADE,
        related_name='user_answers'
    )
    security_answer_hash = models.BinaryField(max_length=60)
    
    class Meta:
        unique_together = ('user', 'question')
        db_table = 'user_security_answer'
    
    def __str__(self):
        return f"{self.user.username} - {self.question.question[:50]}"


class PrefilledDoctor(models.Model):
    """
    Master doctor list that reps can pick from.
    Lives outside doctor_viewer_doctor so that:
    - Prefill table is read-only for reps
    - doctor_viewer_doctor keeps the "per-rep, per-campaign" context
    """
    full_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=120, null=True, blank=True, unique=True)
    phone = models.CharField(max_length=20, null=True, blank=True, unique=True)
    specialty = models.CharField(max_length=120, null=True, blank=True)
    city = models.CharField(max_length=120, null=True, blank=True)
    
    class Meta:
        db_table = 'prefilled_doctor'
    
    def __str__(self):
        return f"{self.full_name} ({self.specialty or 'No specialty'})"


class User(AbstractUser):
    ROLE_CHOICES = (
        ("field_rep", "Field Rep"),
        ("admin", "Admin"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="field_rep")
    google_auth_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    # Field-Rep specific fields
    field_id = models.CharField(
        max_length=50,       # ✔️ recommended in the checklist
        blank=True,
        null=True,
        unique=False,        # ✔️ turn off uniqueness for now unless required
        help_text="Internal ID printed on rep badge/card",
    )


    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        unique=True,
        validators=[RegexValidator(r"^\+?\d{7,15}$")],
        help_text="E.164 format preferred",
    )

    # Field-Rep credentials - nullable columns
    temp_password_hash = models.BinaryField(max_length=60, null=True, blank=True)
    security_answer_hash = models.BinaryField(max_length=60, null=True, blank=True)

    active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['email'], name='idx_user_email'),
        ]

    def __str__(self):
        return f"{self.username} ({self.field_id or self.role})"


class RepLoginOTP(models.Model):
    """
    One-time 6-digit codes for rep WhatsApp login.
    """
    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='login_otp'
    )
    otp_hash = models.BinaryField(max_length=60)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(auto_now_add=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    
    class Meta:
        db_table = 'rep_login_otp'
    
    def __str__(self):
        return f"OTP for {self.user.username} (expires: {self.expires_at})"
    
    def is_expired(self):
        """Check if the OTP has expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class LoginAuditWhatsApp(models.Model):
    """
    Audit trail for WhatsApp login attempts.
    """
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='whatsapp_login_audits'
    )
    success = models.BooleanField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'login_audit_whatsapp'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {'Success' if self.success else 'Failed'} - {self.created_at}"


class Secret(models.Model):
    ENVIRONMENTS = (
        ('dev', 'Development'),
        ('staging', 'Staging'),
        ('production', 'Production'),
    )

    key_name = models.CharField(max_length=100, unique=True)
    key_value = models.TextField()
    environment = models.CharField(max_length=20, choices=ENVIRONMENTS, default='production')
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False  # Don't let Django try to create the table
        db_table = 'secrets'

    def __str__(self):
        return f"{self.key_name} ({self.environment})"
