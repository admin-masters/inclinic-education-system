from django.db import models
from django.utils import timezone
from django.conf import settings
from shortlink_management.models import ShortLink
from collateral_management.models import Collateral

# 🔐 New model
class SecurityQuestion(models.Model):
    question_txt = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.question_txt

class FieldRepresentative(models.Model):
    field_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    email = models.EmailField(blank=True, null=True)
    gmail = models.EmailField(blank=True, null=True)
    whatsapp_number = models.CharField(blank=True, max_length=15, null=True)
    password = models.CharField(blank=True, max_length=255, null=True)
    auth_method = models.CharField(
        choices=[
            ('email', 'Email ID'), 
            ('gmail', 'Gmail ID'), 
            ('whatsapp', 'WhatsApp Number')
        ], 
        default='email', 
        max_length=20
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # 🔐 Security question and answer fields
    security_question = models.ForeignKey(
        SecurityQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    security_answer_hash = models.CharField(max_length=128, blank=True)

    def __str__(self):
        return self.email or self.field_id


class ShareLog(models.Model):
    """
    Logs an event where a field rep shares a short link with a doctor.
    """
    CHANNEL_CHOICES = (
        ('WhatsApp', 'WhatsApp'),
        ('SMS', 'SMS'),
        ('Email', 'Email'),
    )

    short_link = models.ForeignKey(ShortLink, on_delete=models.CASCADE, related_name='share_logs')
    collateral = models.ForeignKey(Collateral, on_delete=models.CASCADE, related_name='share_logs')
    field_rep = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='share_logs')
    doctor_identifier = models.CharField(max_length=255)
    share_channel = models.CharField(max_length=50, choices=CHANNEL_CHOICES, default='WhatsApp')
    share_timestamp = models.DateTimeField(default=timezone.now)
    message_text = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.field_rep.username} shared {self.short_link.short_code} to {self.doctor_identifier}"


class VideoTrackingLog(models.Model):
    """
    Logs video engagement for a doctor/collateral share event.
    """
    share_log = models.ForeignKey(ShareLog, on_delete=models.CASCADE, related_name='video_logs')
    user_id = models.CharField(max_length=255)  # Can be doctor identifier or user id
    video_status = models.PositiveSmallIntegerField()  # 1: 0-50%, 2: 50-99%, 3: 100%
    video_percentage = models.CharField(max_length=10)  # '1', '2', '3' for compatibility
    comment = models.CharField(max_length=255, default='Video Viewed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("share_log", "user_id", "video_percentage")

    def __str__(self):
        return f"{self.user_id} - {self.share_log_id} - {self.video_percentage}"


# ---- NEW MODEL ----
class CollateralTransaction(models.Model):
    """
    One row per (field_rep_id, doctor_number, collateral_id, transaction_date).
    'transaction_id' is a business key (rep*phone*collateral) for easy lookups.
    All *_at fields are optional timestamps for auditing each event.
    """
    # identity
    transaction_id = models.CharField(max_length=128, db_index=True)  # "field_rep_id*doctor_number*collateral_id"
    brand_campaign_id = models.CharField(max_length=64, db_index=True)  # can be int-like or string
    field_rep_id = models.CharField(max_length=64, db_index=True)      # from FIELD_REP_CAMPAIGN
    field_rep_unique_id = models.CharField(max_length=64, blank=True, null=True)

    doctor_name = models.CharField(max_length=255, blank=True, null=True)
    doctor_number = models.CharField(max_length=15, db_index=True)
    doctor_unique_id = models.CharField(max_length=64, blank=True, null=True)

    collateral_id = models.BigIntegerField(db_index=True)
    transaction_date = models.DateField(db_index=True)  # “day-bucket” that decides row uniqueness

    # derived booleans
    has_viewed = models.BooleanField(default=False)             # from link open / verification
    has_downloaded_pdf = models.BooleanField(default=False)     # from download_timestamp
    has_viewed_last_page = models.BooleanField(default=False)   # from last_page_scrolled

    video_view_lt_50 = models.BooleanField(default=False)
    video_view_gt_50 = models.BooleanField(default=False)
    video_view_100 = models.BooleanField(default=False)

    total_video_events = models.PositiveIntegerField(default=0)
    last_video_percentage = models.PositiveSmallIntegerField(default=0)
    last_page_scrolled = models.PositiveIntegerField(default=0)

    # references to last/representative engagement rows (optional, for drill-down)
    doctor_viewer_engagement_id = models.BigIntegerField(blank=True, null=True)
    share_management_engagement_id = models.BigIntegerField(blank=True, null=True)
    video_tracking_last_event_id = models.BigIntegerField(blank=True, null=True)

    # timestamps (mirror existing)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # event timestamps (requested: “Every single activity must have a timestamp stored”)
    sent_at = models.DateTimeField(blank=True, null=True)
    viewed_at = models.DateTimeField(blank=True, null=True)
    downloaded_pdf_at = models.DateTimeField(blank=True, null=True)
    viewed_last_page_at = models.DateTimeField(blank=True, null=True)
    video_lt_50_at = models.DateTimeField(blank=True, null=True)
    video_gt_50_at = models.DateTimeField(blank=True, null=True)
    video_100_at = models.DateTimeField(blank=True, null=True)
    last_video_event_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["brand_campaign_id", "transaction_date"]),
            models.Index(fields=["doctor_number", "collateral_id"]),
        ]
        unique_together = (
            # guarantees SCENARIO rules: same rep+doctor+collateral+same day → single row
            ("field_rep_id", "doctor_number", "collateral_id", "transaction_date"),
        )

    def __str__(self):
        return f"{self.transaction_id} @ {self.transaction_date}"
