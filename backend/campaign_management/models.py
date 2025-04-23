# campaign_management/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone

STATUS_CHOICES = (
    ('Draft', 'Draft'),
    ('Active', 'Active'),
    ('Completed', 'Completed'),
)

class Campaign(models.Model):
    name = models.CharField(max_length=255)
    brand_name = models.CharField(max_length=255)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_campaigns'
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status})"


class CampaignAssignment(models.Model):
    """
    Bridging table between Campaign and Field Reps (User with role='field_rep').
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='assignments')
    field_rep = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaign_assignments')
    assigned_on = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('campaign', 'field_rep')

    def __str__(self):
        return f"{self.field_rep.username} -> {self.campaign.name}"