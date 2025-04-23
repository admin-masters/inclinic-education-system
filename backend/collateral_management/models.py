# collateral_management/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
import os

from campaign_management.models import Campaign  # referencing your existing Campaign
# If you have a separate bridging table there, you can skip defining it again here.

COLLATERAL_TYPE_CHOICES = (
    ('pdf', 'PDF'),
    ('video', 'Video'),
)

def collateral_upload_path(instance, filename):
    """
    Upload to MEDIA_ROOT/collaterals/<collateral_id>/<filename>
    We’ll set collateral_id after saving, so initially we might store temp
    or handle logic in the model's save().
    """
    return f"collaterals/{filename}"

class Collateral(models.Model):
    """
    Stores PDF or video link info.
    """
    type = models.CharField(max_length=10, choices=COLLATERAL_TYPE_CHOICES, default='pdf')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=collateral_upload_path, blank=True, null=True)
    vimeo_url = models.URLField(blank=True, null=True)
    content_id = models.CharField(max_length=100, blank=True, null=True)
    upload_date = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    # For demonstration, let's store who created it (optional)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_collaterals'
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.type})"

# ----------------------------------------------------------------
# Bridging table: Collateral <-> Campaign
# If you already have a "CampaignCollateral" in the campaign app,
# you can skip this definition. Otherwise, here's a standalone version.
# ----------------------------------------------------------------
class CampaignCollateral(models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='campaign_collaterals'
    )
    collateral = models.ForeignKey(
        Collateral,
        on_delete=models.CASCADE,
        related_name='campaign_collaterals'
    )
    # optional scheduling
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('campaign', 'collateral')

    def __str__(self):
        return f"{self.campaign.name} - {self.collateral.title}"