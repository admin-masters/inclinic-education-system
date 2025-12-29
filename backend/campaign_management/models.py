from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
import re

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
        max_length=64, unique=True, db_index=True, blank=True,
        help_text="ID used by marketing / brand team"
    )

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    description = models.TextField(blank=True)

    # ——— NEW fields for the Brand Campaign Form ———
    company_name = models.CharField(max_length=255, blank=True)
    incharge_name = models.CharField(max_length=255, blank=True)
    incharge_contact = models.CharField(max_length=20, blank=True)       # phone, keep string for flexibility
    incharge_designation = models.CharField(max_length=255, blank=True)
    num_doctors = models.PositiveIntegerField(default=0)
    items_per_clinic_per_year = models.PositiveIntegerField(default=0)
    contract = models.FileField(upload_to="campaigns/contracts/", blank=True, null=True)
    brand_logo = models.ImageField(upload_to="campaigns/logos/brand/", blank=True, null=True)
    company_logo = models.ImageField(upload_to="campaigns/logos/company/", blank=True, null=True)
    printing_required = models.BooleanField(default=False)
    printing_excel = models.FileField(upload_to="campaigns/printing/", blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_campaigns'
    )

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def _generate_bcid(self):
        base = re.sub(r'[^A-Za-z0-9]+', '-', (self.brand_name or self.name or 'CMP')).strip('-').upper()[:12]
        return f"{base}-{uuid.uuid4().hex[:6].upper()}"

    def save(self, *args, **kwargs):
        if not self.brand_campaign_id:
            self.brand_campaign_id = self._generate_bcid()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.status})"

# ✅ Add legacy alias so old forms keep working:
Campaign.STATUS_CHOICES = Campaign._meta.get_field("status").choices

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