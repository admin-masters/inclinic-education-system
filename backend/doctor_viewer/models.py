from django.db import models
from django.utils import timezone
from user_management.models import User
from shortlink_management.models import ShortLink
from collateral_management.models import Collateral  # ✅ Make sure to import this

# ─────────────────────────────────────────────
# DOCTOR MODEL – linked to a Field Rep (User)
# ─────────────────────────────────────────────
class Doctor(models.Model):
    rep = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="doctors",  # use `rep.doctors.all()` to access
        limit_choices_to={"role": "field_rep"}
    )
    name = models.CharField("Doctor Name", max_length=100)
    phone = models.CharField("Phone Number", max_length=15, blank=True)
    
    # Source enum to flag rows from pre-filled master-list
    SOURCE_CHOICES = (
        ('manual', 'Manual'),
        ('prefill', 'Pre-filled'),
    )
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default='manual',
        help_text="Source of the doctor record"
    )

    def __str__(self):
        return f"{self.name} ({self.phone})"


# ─────────────────────────────────────────────
# DOCTOR ENGAGEMENT MODEL – PDF/video tracking
# ─────────────────────────────────────────────
class DoctorEngagement(models.Model):
    """
    One row per doctor visit (identified by the short-code).
    Tracks PDF and video progress.
    """
    short_link = models.ForeignKey(
        ShortLink,
        on_delete=models.CASCADE,
        related_name="engagements"
    )
    view_timestamp = models.DateTimeField(default=timezone.now)

    # PDF metrics
    pdf_completed = models.BooleanField(default=False)
    last_page_scrolled = models.PositiveIntegerField(default=0)

    # Video metrics
    video_watch_percentage = models.PositiveIntegerField(default=0)  # 0-100%

    STATUS = (
        (0, "not-started"),
        (1, "in-progress"),
        (2, "completed"),
    )
    status = models.PositiveSmallIntegerField(
        choices=STATUS,
        default=0,
        db_index=True
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.short_link.short_code} @ {self.view_timestamp:%Y-%m-%d %H:%M}"


# ─────────────────────────────────────────────
# DOCTOR-COLLATERAL MAPPING MODEL
# ─────────────────────────────────────────────
class DoctorCollateral(models.Model):
    """Links one doctor to one collateral once it has been ‘registered’."""
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="collateral_links"
    )
    collateral = models.ForeignKey(
        Collateral,
        on_delete=models.CASCADE,
        related_name="doctor_links"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("doctor", "collateral")

    def __str__(self) -> str:
        return f"{self.doctor} ⇒ {self.collateral}"
