from django.db import models
from django.utils import timezone
from django.conf import settings

from shortlink_management.models import ShortLink

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
    field_rep = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='share_logs')
    doctor_identifier = models.CharField(max_length=255)  # Could store phone or name or both
    share_channel = models.CharField(max_length=50, choices=CHANNEL_CHOICES, default='WhatsApp')
    share_timestamp = models.DateTimeField(default=timezone.now)
    message_text = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.field_rep.username} shared {self.short_link.short_code} to {self.doctor_identifier}"
