from django.db import models
from django.utils import timezone
from shortlink_management.models import ShortLink

class DoctorEngagement(models.Model):
    """
    One row per doctor visit (identified by short‑code).
    """
    short_link      = models.ForeignKey(ShortLink, on_delete=models.CASCADE, related_name='engagements')
    view_timestamp  = models.DateTimeField(default=timezone.now)

    # PDF metrics
    pdf_completed       = models.BooleanField(default=False)
    last_page_scrolled  = models.IntegerField(default=0)

    # Video metrics
    video_watch_percentage = models.IntegerField(default=0)      # 0…100

    created_at  = models.DateTimeField(default=timezone.now)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.short_link.short_code} @ {self.view_timestamp:%Y-%m-%d %H:%M}"