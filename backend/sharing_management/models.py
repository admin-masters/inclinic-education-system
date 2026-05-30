# sharing_management/models.py
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import check_password as django_check_password
from django.db import models
from django.utils import timezone


def _master_db_alias() -> str:
    return getattr(settings, "MASTER_DB_ALIAS", "master")


class SecurityQuestion(models.Model):
    """
    Stored in DEFAULT DB.

    Your views expect:
      SecurityQuestion.objects.all().values_list("id", "question_txt")
    """
    question_txt = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sharing_management_securityquestion"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.question_txt


class FieldRepSecurityProfile(models.Model):
    """
    Stored in DEFAULT DB.
    Maps a MASTER field rep (by integer id) to a security question + hashed answer.

    This keeps your forgot/reset-password flow working even though FieldReps live in MASTER DB.
    """
    master_field_rep_id = models.BigIntegerField(unique=True, db_index=True)
    email = models.EmailField(blank=True, default="")

    security_question = models.ForeignKey(
        SecurityQuestion,
        on_delete=models.PROTECT,
        related_name="fieldrep_profiles",
        null=True,
        blank=True,
    )
    security_answer_hash = models.CharField(max_length=128, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sharing_management_fieldrepsecurityprofile"

    def __str__(self) -> str:
        return f"FieldRepSecurityProfile(master_field_rep_id={self.master_field_rep_id})"

    def check_answer(self, raw_answer: str) -> bool:
        if not self.security_answer_hash:
            return False
        return django_check_password(raw_answer or "", self.security_answer_hash)


class ShareLog(models.Model):
    """
    Stored in DEFAULT DB.

    IMPORTANT CHANGE:
      - field_rep_id is now a plain integer (MASTER field rep id),
        NOT a ForeignKey to a local FieldRepresentative/User table.

    We also store field_rep_email for convenience/debug/UI.
    """
    short_link = models.ForeignKey(
        "shortlink_management.ShortLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="share_logs",
    )
    collateral = models.ForeignKey(
        "collateral_management.Collateral",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="share_logs",
    )

    # MASTER DB field rep id (campaign_fieldrep.id)
    field_rep_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    field_rep_email = models.EmailField(blank=True, default="")

    # phone/email identifier for doctor
    doctor_identifier = models.CharField(max_length=255, db_index=True)

    share_channel = models.CharField(max_length=32, blank=True, default="")
    share_timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    message_text = models.TextField(blank=True, default="")
    brand_campaign_id = models.CharField(max_length=32, blank=True, default="", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sharing_management_sharelog"
        indexes = [
            models.Index(fields=["field_rep_id", "share_timestamp"]),
            models.Index(fields=["doctor_identifier", "share_timestamp"]),
            models.Index(fields=["collateral", "share_timestamp"]),
            models.Index(fields=["brand_campaign_id", "share_timestamp"]),
        ]
        ordering = ["-share_timestamp"]

    def __str__(self) -> str:
        return f"ShareLog(id={self.id}, field_rep_id={self.field_rep_id}, doctor={self.doctor_identifier})"

    @property
    def master_field_rep(self):
        """
        Convenience accessor (non-queryable in ORM filters).
        """
        if not self.field_rep_id:
            return None
        try:
            from campaign_management.master_models import MasterFieldRep

            return (
                MasterFieldRep.objects.using(_master_db_alias())
                .select_related("user", "brand")
                .filter(id=self.field_rep_id)
                .first()
            )
        except Exception:
            return None


class VideoTrackingLog(models.Model):
    """
    Stored in DEFAULT DB.
    """
    share_log = models.ForeignKey(ShareLog, on_delete=models.CASCADE, related_name="video_logs")
    user_id = models.CharField(max_length=64, db_index=True)
    video_status = models.CharField(max_length=16)
    video_percentage = models.CharField(max_length=16, blank=True, default="")
    comment = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sharing_management_videotrackinglog"
        indexes = [models.Index(fields=["share_log", "user_id"])]

    def __str__(self) -> str:
        return f"VideoTrackingLog(share_log_id={self.share_log_id}, user_id={self.user_id})"


class CollateralTransaction(models.Model):
    """
    Stored in DEFAULT DB.

    Keep this model aligned with migration 0010 and the existing production table.
    The reporting service writes the durable transaction_id in the format:
    brand-supplied-field-id-doctor-number-collateral-id-datetime.
    """
    transaction_id = models.CharField(max_length=128, db_index=True)
    brand_campaign_id = models.CharField(max_length=64, db_index=True)

    field_rep_id = models.CharField(max_length=64, db_index=True)
    field_rep_unique_id = models.CharField(max_length=64, blank=True, null=True)

    doctor_name = models.CharField(max_length=255, blank=True, null=True)
    doctor_number = models.CharField(max_length=15, db_index=True)
    doctor_unique_id = models.CharField(max_length=64, blank=True, null=True)

    collateral_id = models.BigIntegerField(db_index=True)
    transaction_date = models.DateField(db_index=True)

    has_viewed = models.BooleanField(default=False)
    has_downloaded_pdf = models.BooleanField(default=False)
    has_viewed_last_page = models.BooleanField(default=False)

    video_view_lt_50 = models.BooleanField(default=False)
    video_view_gt_50 = models.BooleanField(default=False)
    video_view_100 = models.BooleanField(default=False)
    total_video_events = models.PositiveIntegerField(default=0)
    last_video_percentage = models.PositiveSmallIntegerField(default=0)
    last_page_scrolled = models.PositiveIntegerField(default=0)

    doctor_viewer_engagement_id = models.BigIntegerField(blank=True, null=True)
    share_management_engagement_id = models.BigIntegerField(blank=True, null=True)
    video_tracking_last_event_id = models.BigIntegerField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    downloaded_pdf_at = models.DateTimeField(null=True, blank=True)
    viewed_last_page_at = models.DateTimeField(null=True, blank=True)
    video_lt_50_at = models.DateTimeField(null=True, blank=True)
    video_gt_50_at = models.DateTimeField(null=True, blank=True)
    video_100_at = models.DateTimeField(null=True, blank=True)
    last_video_event_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sharing_management_collateraltransaction"
        unique_together = (("field_rep_id", "doctor_number", "collateral_id", "transaction_date"),)
        indexes = [
            models.Index(fields=["brand_campaign_id", "transaction_date"]),
            models.Index(fields=["doctor_number", "collateral_id"]),
        ]

    def __str__(self) -> str:
        return self.transaction_id
