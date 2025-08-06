from django.db import models
from django.conf import settings
from django.utils import timezone

STATUS_CHOICES = (
    ('Draft', 'Draft'),
    ('Active', 'Active'),
    ('Completed', 'Completed'),
)

# ✅ Define Collateral FIRST
class Collateral(models.Model):
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='collaterals/')

    def __str__(self):
        return self.item_name

# ✅ Now define Campaign
class Campaign(models.Model):
    name = models.CharField(max_length=255)
    brand_name = models.CharField(max_length=255)

    brand_campaign_id = models.CharField(
        max_length=64, null=False, blank=False,
        help_text="ID used by marketing / brand team"
    )

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

# ✅ CampaignMessage - New model for message templates
class CampaignMessage(models.Model):
    """
    Stores message templates for campaigns that will be sent to doctors
    """
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    message_number = models.CharField(
        max_length=10,
        help_text="Message number/identifier (e.g., 459, 458, etc.)"
    )
    
    message_text = models.TextField(
        help_text="The actual message template"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('campaign', 'message_number')
        ordering = ['message_number']
    
    def __str__(self):
        return f"{self.campaign.brand_campaign_id} - Message {self.message_number}"

# ✅ CampaignAssignment
class CampaignAssignment(models.Model):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='assignments'
    )

    field_rep = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='campaign_assignments_campaign_mgmt'
    )

    assigned_on = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('campaign', 'field_rep')

    def __str__(self):
        return f"{self.field_rep.username} -> {self.campaign.name}"

# ✅ CampaignCollateral
class CampaignCollateral(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='campaign_collaterals')
    collateral = models.ForeignKey(Collateral, on_delete=models.CASCADE, related_name='campaign_collaterals')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.campaign.brand_campaign_id} - {self.collateral.item_name}"
