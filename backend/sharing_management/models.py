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
