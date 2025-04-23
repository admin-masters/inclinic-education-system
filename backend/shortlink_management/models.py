# shortlink_management/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from collateral_management.models import Collateral

RESOURCE_TYPE_CHOICES = (
    ('collateral', 'Collateral'),
    # Add other resource types if needed
)

class ShortLink(models.Model):
    short_code = models.CharField(max_length=50, unique=True)
    resource_type = models.CharField(max_length=50, choices=RESOURCE_TYPE_CHOICES, default='collateral')
    resource_id = models.PositiveIntegerField()  # We'll store Collateral's ID here

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_shortlinks'
    )
    date_created = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    # Timestamps for auditing
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.short_code} -> {self.resource_type}({self.resource_id})"

    def get_collateral(self):
        """
        If resource_type='collateral', fetch the Collateral object.
        """
        if self.resource_type == 'collateral':
            try:
                return Collateral.objects.get(id=self.resource_id)
            except Collateral.DoesNotExist:
                return None
        return None