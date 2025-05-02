from django.db import models
from user_management.models import User                # field reps
from campaign_management.models import Campaign        # existing model

class FieldRepCampaign(models.Model):
    """
    Associates a single Field-Rep (user.role == 'field_rep')
    with a Campaign.  One row per assignment.
    """
    field_rep = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'field_rep'},
        related_name='assigned_campaigns')

    campaign  = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='field_reps')

    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('field_rep', 'campaign')
        verbose_name = "Field-Rep Campaign"
        verbose_name_plural = "Field-Rep Campaigns"

    def __str__(self):
        return f"{self.field_rep} ⇢ {self.campaign}"