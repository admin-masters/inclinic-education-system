from django.db import models
from django.contrib.auth.models import User

# Roles for internal staff
ROLE_CHOICES = (
    ('FIELD_REP', 'Field Representative'),
    ('BRAND_MANAGER', 'Brand Manager'),
    ('ADMIN', 'Administrator'),
)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='FIELD_REP')

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class Campaign(models.Model):
    campaign_name = models.CharField(max_length=255)
    therapy_area = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, default='ACTIVE')  # ACTIVE, COMPLETED, ARCHIVED
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    exported_at = models.DateTimeField(null=True, blank=True)  # for data export

    def __str__(self):
        return self.campaign_name

class CampaignContent(models.Model):
    CONTENT_TYPE_CHOICES = (
        ('PDF', 'PDF'),
        ('VIDEO', 'VIDEO'),
    )
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES)
    content_title = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, null=True, blank=True)
    vimeo_url = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    exported_at = models.DateTimeField(null=True, blank=True)  # for data export

    def __str__(self):
        return f"{self.campaign} - {self.content_title}"

class DoctorShare(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    content = models.ForeignKey(CampaignContent, on_delete=models.CASCADE)
    rep = models.ForeignKey(User, on_delete=models.CASCADE)
    doctor_phone = models.CharField(max_length=20)
    share_timestamp = models.DateTimeField(auto_now_add=True)
    exported_at = models.DateTimeField(null=True, blank=True)  # for data export

    def __str__(self):
        return f"Share: {self.campaign} - {self.doctor_phone}"

class PDFEvent(models.Model):
    EVENT_CHOICES = (
        ('OPEN', 'OPEN'),
        ('DOWNLOAD', 'DOWNLOAD'),
        ('COMPLETE', 'COMPLETE'),
    )
    share = models.ForeignKey(DoctorShare, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    event_timestamp = models.DateTimeField(auto_now_add=True)
    exported_at = models.DateTimeField(null=True, blank=True)  # for data export

    def __str__(self):
        return f"{self.share} - {self.event_type}"

class VideoEvent(models.Model):
    EVENT_CHOICES = (
        ('PLAY', 'PLAY'),
        ('WATCH_TIME', 'WATCH_TIME'),
        ('COMPLETE', 'COMPLETE'),
    )
    share = models.ForeignKey(DoctorShare, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    watch_seconds = models.IntegerField(null=True, blank=True)
    event_timestamp = models.DateTimeField(auto_now_add=True)
    exported_at = models.DateTimeField(null=True, blank=True)  # for data export

    def __str__(self):
        return f"{self.share} - {self.event_type}"

