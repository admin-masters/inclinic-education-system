from django.db import models
from collateral_management.models import Collateral
from shortlink_management.models import ShortLink


class SecurityQuestion(models.Model):
    question_text = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.question_text


class ShareLog(models.Model):
    """
    Lives in DEFAULT DB.
    References MASTER field rep by ID only (no FK), to avoid cross-db constraints/joins.
    Store MasterFieldRep.id in field_rep_id.
    """
    short_link = models.ForeignKey(
        ShortLink, on_delete=models.CASCADE, related_name="share_logs"
    )
    collateral = models.ForeignKey(
        Collateral, on_delete=models.CASCADE, related_name="share_logs"
    )

    # MASTER DB id (campaign_fieldrep.id)
    field_rep_id = models.PositiveIntegerField(db_index=True)

    doctor_identifier = models.CharField(max_length=100, blank=True, default="")
    doctor_unique_id = models.CharField(max_length=100, blank=True, default="")

    share_channel = models.CharField(max_length=50, blank=True, default="")
    share_timestamp = models.DateTimeField(auto_now_add=True)

    message_text = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ShareLog({self.id}) rep={self.field_rep_id} collateral={self.collateral_id}"


class VideoTrackingLog(models.Model):
    """
    DEFAULT DB.
    """
    share_log = models.ForeignKey(
        ShareLog, on_delete=models.CASCADE, related_name="video_tracking"
    )
    user_id = models.CharField(max_length=50, db_index=True)
    current_time = models.FloatField(default=0)
    duration = models.FloatField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("share_log", "user_id")

    def __str__(self):
        return f"Tracking({self.user_id}) for ShareLog({self.share_log_id})"


class CollateralTransaction(models.Model):
    """
    DEFAULT DB.
    This stores analytics/transaction state only.
    """
    transaction_id = models.CharField(max_length=64, unique=True, db_index=True)
    short_link_id = models.CharField(max_length=64, db_index=True)

    doctor_name = models.CharField(max_length=255, blank=True, default="")
    doctor_phone = models.CharField(max_length=20, blank=True, default="")
    doctor_unique_id = models.CharField(max_length=64, blank=True, default="")

    field_rep_id = models.CharField(max_length=64, blank=True, default="")
    field_rep_unique_id = models.CharField(max_length=100, blank=True, default="")

    brand_campaign_id = models.CharField(max_length=64, blank=True, default="")
    collateral_id = models.CharField(max_length=64, blank=True, default="")

    TRANSACTION_STATUS_CHOICES = [
        ("sent", "Sent"),
        ("opened", "Opened"),
        ("clicked", "Clicked"),
        ("downloaded", "Downloaded"),
        ("video_viewed", "Video Viewed"),
    ]
    transaction_status = models.CharField(
        max_length=32, choices=TRANSACTION_STATUS_CHOICES, default="sent"
    )

    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    video_viewed_at = models.DateTimeField(null=True, blank=True)

    pdf_pages_viewed = models.JSONField(null=True, blank=True)
    video_watch_seconds = models.FloatField(default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_id} ({self.transaction_status})"
