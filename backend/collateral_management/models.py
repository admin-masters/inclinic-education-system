from django.db import models
from django.conf import settings
from django.utils import timezone


# ------------------------------------------------------------------
# helper: where uploaded files go
# ------------------------------------------------------------------
def collateral_upload_path(instance, filename):
    """
    MEDIA_ROOT/collaterals/<id or tmp>/<filename>
    """
    return f"collaterals/{instance.id or 'tmp'}/{filename}"


# ------------------------------------------------------------------
# look-up tables
# ------------------------------------------------------------------
COLLATERAL_TYPE_CHOICES = (
    ("pdf",   "PDF"),
    ("video", "Video"),
)

PURPOSE_CHOICES = (
    ("Doctor education short",      "Doctor education short"),
    ("Doctor education long",       "Doctor education long"),
    ("Patient education compliance","Patient education compliance"),
    ("Patient education general",   "Patient education general"),
)


# ------------------------------------------------------------------
# main model
# ------------------------------------------------------------------
class Collateral(models.Model):
    # relations -----------------------------------------------------
    campaign    = models.ForeignKey(
        "campaign_management.Campaign",
        on_delete=models.CASCADE,
        related_name="collaterals",
        null=True,
    )
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_collaterals",
    )

    # business fields ----------------------------------------------
    purpose     = models.CharField(max_length=50, choices=PURPOSE_CHOICES, default="Doctor education short")

    title       = models.CharField(max_length=255)
    type        = models.CharField(max_length=10, choices=COLLATERAL_TYPE_CHOICES)

    file        = models.FileField(upload_to=collateral_upload_path, blank=True, null=True)
    vimeo_url   = models.URLField(blank=True, null=True)
    content_id  = models.CharField(max_length=100, blank=True, null=True)

    banner_1    = models.ImageField(upload_to=collateral_upload_path, blank=True, null=True)
    banner_2    = models.ImageField(upload_to=collateral_upload_path, blank=True, null=True)

    description = models.CharField(max_length=255, blank=True)

    # NEW: Optional doctor name for display
    doctor_name = models.CharField(max_length=255, blank=True)

    # NEW: Optional webinar fields
    webinar_title = models.CharField(max_length=255, blank=True)
    webinar_description = models.TextField(blank=True)
    webinar_url = models.URLField(blank=True)
    webinar_date = models.DateField(null=True, blank=True)

    # meta / flags --------------------------------------------------
    is_active   = models.BooleanField(default=True)
    upload_date = models.DateTimeField(default=timezone.now)
    created_at  = models.DateTimeField(default=timezone.now)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    # pretty name ---------------------------------------------------
    def __str__(self):
        return f"{self.title} ({self.type})"
    
    # helper (optional)
    def webinar_month_year(self):
        if self.webinar_date:
            return self.webinar_date.strftime("%B %Y")
        return None


# ------------------------------------------------------------------
# bridging table  Campaign  ↔  Collateral
# ------------------------------------------------------------------
class CampaignCollateral(models.Model):
    campaign   = models.ForeignKey(
        "campaign_management.Campaign",
        on_delete=models.CASCADE,
        related_name="collateral_campaign_collaterals"
    )
    collateral = models.ForeignKey(
        Collateral,
        on_delete=models.CASCADE,
        related_name="campaign_collaterals",
    )
    start_date = models.DateTimeField(blank=True, null=True)
    end_date   = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("campaign", "collateral")

    def __str__(self):
        return f"{self.campaign.name} – {self.collateral.title}"
