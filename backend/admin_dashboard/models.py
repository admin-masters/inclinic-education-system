from django.db import models
import uuid


class FieldRepCampaign(models.Model):
    """
    Associates a single Field-Rep (user.role == 'field_rep')
    with a Campaign. One row per assignment.
    """

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    field_rep = models.ForeignKey(
        "user_management.User",   # ✅ lazy reference avoids circular import
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'field_rep'},
        related_name='assigned_campaigns'
    )

    campaign = models.ForeignKey(
        "campaign_management.Campaign",   # ✅ lazy reference
        on_delete=models.CASCADE,
        related_name='field_reps'
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('field_rep', 'campaign')
        verbose_name = "Field-Rep Campaign"
        verbose_name_plural = "Field-Rep Campaigns"

    def brand_campaign_id(self):
        return self.campaign.brand_campaign_id

    def gmail(self):
        return self.field_rep.email

    def phone(self):
        return self.field_rep.phone_number

    def __str__(self):
        return f"{self.field_rep} ⇢ {self.campaign}"
