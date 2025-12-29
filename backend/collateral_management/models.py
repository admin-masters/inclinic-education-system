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
    upload_path = f"collaterals/{instance.id or 'tmp'}/{filename}"
    print(f"[collateral_upload_path] Uploading file '{filename}' to path: {upload_path}")
    print(f"[collateral_upload_path] Instance ID: {instance.id or 'tmp'}, Instance: {instance}")
    return upload_path
    


# ------------------------------------------------------------------
# look-up tables
# ------------------------------------------------------------------
COLLATERAL_TYPE_CHOICES = (
    ("pdf",   "PDF"),
    ("video", "Video"),
    ("pdf_video", "PDF + Video"),
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
        return self.title
        
    def save(self, *args, **kwargs):
        # If this is a video type, ensure the Vimeo URL is properly formatted
        if self.type in ['video', 'pdf_video'] and self.vimeo_url:
            # If it's a full Vimeo URL, extract just the video ID
            if 'vimeo.com' in self.vimeo_url:
                # Remove any query parameters
                clean_url = self.vimeo_url.split('?')[0]
                # Extract the video ID (handles both /video/123 and /123 formats)
                if '/video/' in clean_url:
                    self.vimeo_url = clean_url.split('/video/')[-1]
                else:
                    self.vimeo_url = clean_url.strip('/').split('/')[-1]
        
        super().save(*args, **kwargs)
    
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
